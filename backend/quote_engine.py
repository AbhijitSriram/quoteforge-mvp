# backend/quote_engine.py
import math
import re
from typing import Dict, Any, Optional

# ---- Tunable constants -------------------------------------------------

# Baseline machining rate ($/min)
DEFAULT_MACHINE_RATE = 2.0

# Approximate density in lb / in^3
MATERIAL_DENSITY_LB_PER_IN3: Dict[str, float] = {
    "aluminum": 0.0975,
    "aluminium": 0.0975,
    "steel": 0.283,
    "mild steel": 0.283,
    "stainless": 0.290,
    "stainless steel": 0.290,
    "titanium": 0.160,
}

# “Rules of thumb” machining time (per part) by complexity
COMPLEXITY_BASE_TIME_MIN: Dict[str, int] = {
    "simple": 30,
    "moderate": 60,
    "complex": 120,
}

# Size scaling factor
SIZE_FACTOR: Dict[str, float] = {
    "small": 1.0,
    "medium": 1.3,
    "large": 1.8,
}

# Tolerance / difficulty multiplier
TOLERANCE_FACTOR: Dict[str, float] = {
    "normal": 1.0,
    "tight": 1.3,
    "aerospace": 1.7,
}

# ------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------


def _norm(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s.strip().lower() or None


def estimate_weight_lbs(inputs: Dict[str, Any]) -> Optional[float]:
    """
    Try to estimate per-part weight from length/width/height + material.
    Returns None if we don't have enough info.
    """
    if inputs.get("material_weight_lbs") is not None:
        return float(inputs["material_weight_lbs"])

    material = _norm(inputs.get("material"))
    if not material:
        return None

    length_in = inputs.get("length_in")
    width_in = inputs.get("width_in")
    height_in = inputs.get("height_in")

    if not (length_in and width_in and height_in):
        # Not enough geometry info
        return None

    density = MATERIAL_DENSITY_LB_PER_IN3.get(material)
    if density is None:
        return None

    volume_in3 = float(length_in) * float(width_in) * float(height_in)
    weight = volume_in3 * density
    return round(weight, 2)


def estimate_machining_minutes(inputs: Dict[str, Any]) -> Optional[int]:
    """
    Estimate per-part machining time from complexity + size.
    """
    if inputs.get("machining_minutes") is not None:
        return int(inputs["machining_minutes"])

    complexity = _norm(inputs.get("complexity")) or "moderate"
    size = _norm(inputs.get("size")) or "medium"

    base = COMPLEXITY_BASE_TIME_MIN.get(complexity)
    size_mult = SIZE_FACTOR.get(size, 1.0)

    if base is None:
        return None

    est = base * size_mult
    return int(round(est))


# ------------------------------------------------------------------------
# Signal extraction (text-based)
# ------------------------------------------------------------------------


def _extract_dimensions(text: str) -> Dict[str, Optional[float]]:
    """
    Extract dimensions from text. Looks for patterns like:
    - "L: 5.5" or "Length: 5.5" or "L = 5.5"
    - "W: 3.2" or "Width: 3.2"
    - "H: 2.1" or "Height: 2.1" or "Thickness: 2.1"
    - Also handles formats like "5.5\" x 3.2\" x 2.1\"" or "5.5 x 3.2 x 2.1"
    - Handles lists like "1.00" 1.00" 3.00" (extracts first 3 distinct values)
    - Handles standalone numbers from OCR (like "30 18 26")
    """
    if not text:
        return {"length_in": None, "width_in": None, "height_in": None}
    
    t = text.lower()
    result = {"length_in": None, "width_in": None, "height_in": None}
    
    # Debug: log what we're working with
    print(f"[DEBUG] Extracting dimensions from text (length={len(text)}): {text[:200]}")
    
    # Pattern 1: Explicit labels like "L:", "Length:", "length =", etc.
    patterns = {
        "length_in": [
            r'\b(?:length|l|len)\s*[=:]\s*([\d.]+)',
            r'\b(?:length|l|len)\s+([\d.]+)',
            r'\b([\d.]+)\s*(?:in|inch|inches|")\s*[x×]\s*([\d.]+)\s*(?:in|inch|inches|")\s*[x×]\s*([\d.]+)\s*(?:in|inch|inches|")',
        ],
        "width_in": [
            r'\b(?:width|w|wide)\s*[=:]\s*([\d.]+)',
            r'\b(?:width|w|wide)\s+([\d.]+)',
        ],
        "height_in": [
            r'\b(?:height|h|thickness|t|ht|thick)\s*[=:]\s*([\d.]+)',
            r'\b(?:height|h|thickness|t|ht|thick)\s+([\d.]+)',
        ],
    }
    
    # Try explicit label patterns first
    for dim_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            matches = re.findall(pattern, t, re.IGNORECASE)
            if matches:
                if dim_type == "length_in" and isinstance(matches[0], tuple) and len(matches[0]) == 3:
                    # Format: "5.5" x 3.2" x 2.1"
                    result["length_in"] = float(matches[0][0])
                    result["width_in"] = float(matches[0][1])
                    result["height_in"] = float(matches[0][2])
                    return result
                else:
                    # Single dimension
                    val = float(matches[0]) if isinstance(matches[0], str) else float(matches[0][0])
                    # Convert mm to inches if the text indicates mm units
                    # Check around the matched pattern for "mm" unit indicators
                    if "mm" in text.lower():
                        # Check if this specific dimension value is followed by "mm"
                        pattern_with_context = r'\b(?:length|l|len|width|w|wide|height|h|thickness|t|ht|thick)\s*[=:]\s*([\d.]+)\s*mm'
                        if re.search(pattern_with_context, text, re.IGNORECASE):
                            val = val / 25.4
                    result[dim_type] = val
                    break
    
    # Pattern 2: "L x W x H" format without labels (e.g., "5.5 x 3.2 x 2.1")
    # This is more aggressive, so only use if we haven't found explicit labels
    if result["length_in"] is None:
        dim_pattern = r'\b([\d.]+)\s*[x×]\s*([\d.]+)\s*[x×]\s*([\d.]+)\b'
        matches = re.findall(dim_pattern, text)
        if matches:
            # Use the first match
            dims = [float(x) for x in matches[0]]
            # Assume largest is length, smallest is height, middle is width
            dims_sorted = sorted(dims, reverse=True)
            result["length_in"] = dims_sorted[0]
            result["width_in"] = dims_sorted[1]
            result["height_in"] = dims_sorted[2]
    
    # Pattern 3: Extract dimensions from lists like "1.00" 2.00" 3.00" or 1.00" 2.00" 3.00"
    # Look for numbers with quotes/inches that might be dimensions
    # Also handle pure numbers from OCR (like "30 18 26")
    inch_matches = []  # Initialize here so it's available for all code paths
    
    # Always try to extract dimensions, even if earlier patterns didn't work
    if result["length_in"] is None:
        # Pattern to find all numbers followed by quote marks (inches)
        # Try multiple patterns to handle different quote styles and escapes
        inch_patterns = [
            r'([\d.]+)\s*[""]',  # Straight or curly quotes - most common
            r'([\d.]+)\s*\\?[""]',  # With optional backslash (for escaped quotes in strings)
            r'([\d.]+)\s*(?:in|inch|inches|")',  # Explicit "in" or quote mark
        ]
        
        # Try each pattern until we get matches
        for pattern in inch_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            # Filter out invalid matches (like just dots or non-numeric)
            valid_matches = []
            for m in matches:
                try:
                    float(m)  # Check if it's a valid number
                    valid_matches.append(m)
                except (ValueError, TypeError):
                    continue
            if valid_matches and len(valid_matches) >= 1:
                inch_matches = valid_matches
                break
        
        # If no valid matches with quotes, try finding just numbers that might be dimensions
        # This is a fallback for cases where quotes are missing or different characters
        if not inch_matches or len(inch_matches) == 0:
            # Look for sequences of decimal numbers that might be dimensions
            # Pattern: number followed by optional space and quote-like character or end
            fallback_pattern = r'([\d.]+)\s*["""'']?\s'
            fallback_matches = re.findall(fallback_pattern, text)
            if fallback_matches and len(fallback_matches) >= 1:
                inch_matches = fallback_matches
            
            # Last resort: just find all decimal numbers and filter by reasonable size
            # This handles technical drawings with pure numbers (often in mm)
            if not inch_matches:
                # More aggressive pattern to catch all numbers, including those in OCR text
                # Also handle numbers with dimension symbols like Ø76, R2, etc.
                number_patterns = [
                    r'Ø\s*(\d+\.?\d*)',  # Diameter symbol: Ø76, Ø48, etc.
                    r'R\s*(\d+\.?\d*)',  # Radius symbol: R2, R5, etc.
                    r'(\d+\.?\d*)',      # Plain numbers: 26, 18, 7, etc.
                ]
                
                all_numbers = []
                for pattern in number_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    all_numbers.extend(matches)
                
                # Remove duplicates while preserving order
                seen_nums = set()
                unique_numbers = []
                for num in all_numbers:
                    if num not in seen_nums:
                        seen_nums.add(num)
                        unique_numbers.append(num)
                all_numbers = unique_numbers
                print(f"[DEBUG] Found {len(all_numbers)} numbers: {all_numbers[:20]}")
                print(f"[DEBUG] Full text for context:\n{text[:500]}\n")
                
                # Filter to reasonable dimension sizes
                # For inches: 0.1 to 100
                # For mm: 1 to 2500 (which is ~100 inches)
                potential_dims = []
                seen_rounded = set()
                max_val = 0
                
                for num_str in all_numbers:
                    try:
                        num = float(num_str)
                        num_rounded = round(num, 2)
                        # Accept dimensions in reasonable range for either inches or mm
                        # Exclude very small numbers (< 1) and very large ones (> 2500)
                        # Also exclude common drawing metadata numbers:
                        # - Sheet numbers (usually 1, 2, etc. - too small)
                        # - Drawing numbers with letters (handled separately)
                        # - Revision numbers (usually single digits)
                        # - Scale denominators (like 1:1, we want the 1 but not as dimension)
                        # Filter more aggressively - exclude very small numbers that are likely metadata
                        # For technical drawings, actual dimensions are usually:
                        # - 5mm and above for small features
                        # - 10mm+ for typical part dimensions
                        # - 20mm+ for main dimensions
                        if 5 <= num <= 2500 and num_rounded not in seen_rounded:
                            # Prefer numbers that are likely dimensions:
                            # - Numbers > 10 are more likely to be dimensions
                            # - Numbers that appear near dimension symbols (Ø, R) are prioritized
                            potential_dims.append((num_str, num))
                            seen_rounded.add(num_rounded)
                            max_val = max(max_val, num)
                            if len(potential_dims) >= 20:  # Get more values to choose best
                                break
                        elif 1 <= num < 5:
                            # Very small numbers (1-4) are likely metadata unless they have dimension symbols
                            # We'll check for symbols in the filtering step
                            potential_dims.append((num_str, num))
                            seen_rounded.add(num_rounded)
                            max_val = max(max_val, num)
                    except:
                        continue
                
                # Sort by value (larger numbers are more likely to be main dimensions)
                # Prioritize numbers that appear with dimension symbols (Ø, R) or in dimension contexts
                # Filter out likely metadata (very small numbers, numbers near "SHEET", "REV", etc.)
                filtered_dims = []
                text_lower = text.lower()
                
                for num_str, num_val in potential_dims:
                    num_pos = text.find(num_str)
                    if num_pos < 0:
                        continue
                    
                    # Get context around the number
                    context_start = max(0, num_pos - 30)
                    context_end = min(len(text), num_pos + len(num_str) + 30)
                    context = text[context_start:context_end].lower()
                    nearby_text = text[max(0, num_pos-10):min(len(text), num_pos+len(num_str)+10)]
                    
                    # Skip if number appears near metadata keywords
                    metadata_keywords = ['sheet', 'rev', 'drawing number', 'scale', 'weight', 'date', 'drawn by', 'checked by', 'designed by', 'a4', 'edst']
                    if any(keyword in context for keyword in metadata_keywords):
                        print(f"[DEBUG] Skipping {num_str} (near metadata)")
                        continue
                    
                    # Prioritize numbers that appear with dimension symbols or in dimension contexts
                    priority = 0
                    if 'Ø' in nearby_text or 'ø' in nearby_text:
                        priority = 3  # Highest priority - diameter dimensions
                        print(f"[DEBUG] High priority: {num_str} (diameter symbol)")
                    elif 'R' in nearby_text or 'r' in nearby_text:
                        priority = 2  # High priority - radius dimensions
                        print(f"[DEBUG] High priority: {num_str} (radius symbol)")
                    elif any(word in context for word in ['view', 'section', 'front', 'length', 'width', 'height', 'depth']):
                        priority = 1  # Medium priority - dimension-related context
                        print(f"[DEBUG] Medium priority: {num_str} (dimension context)")
                    elif num_val > 20:  # Larger numbers are more likely to be dimensions
                        priority = 0.5
                    
                    # Lower priority for very small numbers (likely not dimensions)
                    # But don't penalize if they have dimension symbols
                    if num_val < 5 and priority < 2:
                        priority -= 2  # More aggressive penalty for small numbers without symbols
                    elif num_val < 10 and priority < 1:
                        priority -= 0.5  # Slight penalty for medium-small numbers
                    
                    # Boost priority for numbers in the typical dimension range (10-100)
                    if 10 <= num_val <= 100:
                        priority += 0.3
                    elif 20 <= num_val <= 200:
                        priority += 0.5  # Even higher boost for main dimensions
                    
                    filtered_dims.append((num_str, num_val, priority))
                
                # Count frequency of each number (numbers that appear multiple times are more likely to be dimensions)
                num_counts = {}
                for num_str, num_val, _ in filtered_dims:
                    num_counts[num_str] = num_counts.get(num_str, 0) + 1
                
                # Boost priority for numbers that appear multiple times
                for i, (num_str, num_val, priority) in enumerate(filtered_dims):
                    if num_counts.get(num_str, 0) > 1:
                        filtered_dims[i] = (num_str, num_val, priority + 0.5)
                        print(f"[DEBUG] Boosted priority for {num_str} (appears {num_counts[num_str]} times)")
                
                # Sort: highest priority first, then by value (descending), then by frequency
                # But give extra weight to larger numbers in the typical dimension range
                filtered_dims.sort(key=lambda x: (
                    -x[2],  # Priority first (highest first)
                    -(x[1] if 10 <= x[1] <= 200 else x[1] * 0.5),  # Boost numbers in 10-200 range
                    -num_counts.get(x[0], 0)  # Frequency
                ))
                print(f"[DEBUG] Filtered and sorted dimensions: {[(x[0], x[1], f'priority={x[2]:.1f}', f'count={num_counts.get(x[0], 1)}') for x in filtered_dims[:15]]}")
                
                # Take the top dimensions, prioritizing those with dimension symbols
                # For technical drawings, actual dimensions are usually:
                # - Larger numbers (10-100+ mm for typical parts)
                # - Associated with dimension symbols (Ø, R)
                # - Not near metadata keywords
                
                # Filter out very small numbers that are likely not dimensions
                # For technical drawings, actual part dimensions are usually:
                # - 10mm+ for typical features  
                # - 20mm+ for main dimensions
                # - Small numbers (1-9) are usually metadata unless they have dimension symbols
                # Prioritize numbers in the 10-200 range (typical part dimensions in mm)
                
                # First, try to get dimensions >= 10 (most likely to be actual part dimensions)
                significant_dims = [x for x in filtered_dims if x[1] >= 10]
                
                # If we don't have enough, include smaller numbers with high priority
                if len(significant_dims) < 3:
                    additional = [x for x in filtered_dims if x[1] >= 5 and x[2] >= 1 and x not in significant_dims]
                    significant_dims.extend(additional)
                
                high_priority_dims = [x for x in significant_dims if x[2] >= 2]
                medium_priority_dims = [x for x in significant_dims if 1 <= x[2] < 2]
                low_priority_dims = [x for x in significant_dims if x[2] < 1]
                
                print(f"[DEBUG] Significant dims breakdown: high={len(high_priority_dims)}, medium={len(medium_priority_dims)}, low={len(low_priority_dims)}")
                print(f"[DEBUG] All significant dims: {[(x[0], x[1], f'p={x[2]:.1f}') for x in significant_dims[:10]]}")
                
                # Always prefer larger numbers (>= 10) over smaller ones
                # Sort significant_dims by value descending first, then by priority
                significant_dims.sort(key=lambda x: (-x[1], -x[2]))  # Value first (largest), then priority
                
                if len(significant_dims) >= 3:
                    # Take top 3-5 by value (largest numbers)
                    potential_dims = [str(x[0]) for x in significant_dims[:5]]
                    print(f"[DEBUG] Using top significant dimensions by value: {potential_dims}")
                elif len(high_priority_dims) >= 3:
                    potential_dims = [str(x[0]) for x in high_priority_dims[:10]]
                    print(f"[DEBUG] Using high-priority dimensions with symbols: {potential_dims}")
                elif len(high_priority_dims) + len(medium_priority_dims) >= 3:
                    # Combine high and medium priority, sorted by value
                    combined = high_priority_dims + medium_priority_dims
                    combined.sort(key=lambda x: (-x[1], -x[2]))  # Value first
                    potential_dims = [str(x[0]) for x in combined[:10]]
                    print(f"[DEBUG] Using combined high/medium priority dimensions: {potential_dims}")
                else:
                    # Last resort: use top dimensions by value (largest first)
                    filtered_dims.sort(key=lambda x: -x[1])  # Sort by value descending
                    potential_dims = [str(x[0]) for x in filtered_dims[:10]]
                    print(f"[DEBUG] Using top dimensions by value (fallback): {potential_dims}")
                
                print(f"[DEBUG] Filtered to {len(potential_dims)} potential dimensions: {potential_dims}")
                
                if len(potential_dims) >= 1:
                    # For technical drawings, numbers are often in millimeters
                    # Try both interpretations: as-is (inches) and converted from mm
                    # If max value > 10, likely mm (common drawing dimensions like 26mm, 76mm, etc.)
                    # If all values < 100 and some > 20, likely mm
                    has_large_values = max_val > 20
                    is_likely_mm = has_large_values or (max_val > 10 and len(potential_dims) >= 2)
                    
                    print(f"[DEBUG] max_val={max_val}, is_likely_mm={is_likely_mm}, potential_dims={potential_dims}")
                    
                    if is_likely_mm:
                        # Convert all from mm to inches
                        potential_dims_inches = []
                        for num_str in potential_dims:
                            try:
                                num_mm = float(num_str)
                                num_inches = num_mm / 25.4
                                if 0.1 <= num_inches <= 100:  # Valid inch range after conversion
                                    potential_dims_inches.append(num_inches)
                            except:
                                continue
                        print(f"[DEBUG] Converted {len(potential_dims_inches)} dimensions from mm to inches: {potential_dims_inches}")
                        if len(potential_dims_inches) >= 1:
                            # Use converted values (even if we only have 1 or 2)
                            inch_matches = [str(round(n, 2)) for n in potential_dims_inches[:5]]
                        else:
                            # Fall back to original (maybe they were inches after all)
                            inch_matches = potential_dims[:5]
                    else:
                        # Assume inches if values are small
                        print(f"[DEBUG] Assuming inches (small values): {potential_dims}")
                        inch_matches = potential_dims[:5]
        # Process extracted dimension values (handle 1, 2, or 3+ dimensions)
        print(f"[DEBUG] inch_matches before processing: {inch_matches}")
        
        # Filter out invalid matches first (like just dots or non-numeric strings)
        valid_inch_matches = []
        for val_str in inch_matches:
            try:
                val = float(val_str)
                if 0.1 <= val <= 2500:  # Valid range before conversion
                    valid_inch_matches.append(val_str)
            except (ValueError, TypeError):
                continue
        
        print(f"[DEBUG] Valid inch_matches after filtering: {valid_inch_matches}")
        
        # Sort by value (largest first) to prioritize actual dimensions over metadata
        # This ensures we process 26, 18, 7 before 8, 5, 4
        if len(valid_inch_matches) >= 1:
            # Convert to tuples (value, string) for sorting
            valid_with_values = []
            for val_str in valid_inch_matches:
                try:
                    val = float(val_str)
                    valid_with_values.append((val, val_str))
                except:
                    continue
            
            # Sort by value descending (largest first)
            valid_with_values.sort(key=lambda x: -x[0])
            valid_inch_matches = [x[1] for x in valid_with_values]
            print(f"[DEBUG] Sorted valid_inch_matches by value (largest first): {valid_inch_matches[:10]}")
            
            # Check max value
            max_temp_val = valid_with_values[0][0] if valid_with_values else 0
            
            # If max value is small (< 10), these are likely metadata, not dimensions
            # Re-extract numbers from text to find larger dimension values
            if max_temp_val < 10:
                print(f"[DEBUG] Max value {max_temp_val} is small, re-extracting to find larger dimensions...")
                # Re-run number extraction to find larger numbers
                number_pattern = r'(\d+\.?\d*)'
                all_numbers = re.findall(number_pattern, text)
                # Filter to numbers >= 10 (more likely to be actual dimensions)
                larger_numbers = []
                for num_str in all_numbers:
                    try:
                        num = float(num_str)
                        if 10 <= num <= 2500:  # Typical dimension range
                            larger_numbers.append((num_str, num))
                    except:
                        continue
                
                # Sort by value (largest first)
                larger_numbers.sort(key=lambda x: -x[1])
                if len(larger_numbers) >= 3:
                    # Replace valid_inch_matches with larger numbers
                    valid_inch_matches = [str(x[0]) for x in larger_numbers[:5]]
                    print(f"[DEBUG] Found larger dimensions: {valid_inch_matches}")
                    max_temp_val = larger_numbers[0][1] if larger_numbers else 0
        
        if len(valid_inch_matches) >= 1:
            # Check if these are likely millimeters (values > 20 are almost certainly mm in technical drawings)
            temp_vals = []
            for val_str in valid_inch_matches[:10]:  # Check more values
                try:
                    temp_vals.append(float(val_str))
                except:
                    continue
            
            max_temp_val = max(temp_vals) if temp_vals else 0
            is_likely_mm = max_temp_val > 20  # Technical drawings with values > 20 are usually mm
            
            print(f"[DEBUG] max_temp_val={max_temp_val}, is_likely_mm={is_likely_mm}")
            
            # Get distinct values, convert to float, and convert mm to inches if needed
            # Process in order of value (largest first) to get the main dimensions
            dims = []
            seen = set()
            
            # Convert all values, but sort by ORIGINAL value (before conversion) to prioritize larger dimensions
            # Then convert and take top 3
            converted_vals = []
            for val_str in valid_inch_matches:
                try:
                    val_original = float(val_str)
                    
                    # Convert from mm to inches if likely mm
                    # If we detected mm (max > 20), convert ALL numbers in the typical dimension range
                    if is_likely_mm:
                        # Convert all numbers that could be dimensions (>= 5mm)
                        # Very small numbers (< 5) might be metadata even in mm drawings
                        if val_original >= 5:
                            val_inches = val_original / 25.4
                            print(f"[DEBUG] Converted {val_str}mm to {val_inches:.2f} inches")
                        else:
                            # Very small numbers, keep as-is (might be inches or metadata)
                            val_inches = val_original
                    else:
                        val_inches = val_original
                    
                    # Round to 2 decimals
                    val_rounded = round(val_inches, 2)
                    # Only add valid dimensions (0.1 to 100 inches)
                    if val_rounded not in seen and 0.1 <= val_inches <= 100:
                        # Store: (original_value, converted_value, rounded_value)
                        # We'll sort by original value to prioritize larger dimensions
                        converted_vals.append((val_original, val_inches, val_rounded))
                        seen.add(val_rounded)
                except (ValueError, TypeError) as e:
                    print(f"[DEBUG] Error converting {val_str}: {e}")
                    continue
            
            # Sort by ORIGINAL value descending (largest first) to get main dimensions
            # This ensures 26, 18, 7 are selected over 8, 5, 4
            converted_vals.sort(key=lambda x: -x[0])  # Sort by original value
            dims = [x[1] for x in converted_vals[:3]]  # Take top 3 converted values
            print(f"[DEBUG] Selected dimensions (original->converted): {[(x[0], x[1]) for x in converted_vals[:3]]}")
            
            print(f"[DEBUG] Final dims list (sorted by value): {dims}")
            
            if len(dims) >= 3:
                # Sort by size: largest = length, smallest = height, middle = width
                dims_sorted = sorted(dims, reverse=True)
                result["length_in"] = dims_sorted[0]
                result["width_in"] = dims_sorted[1]
                result["height_in"] = dims_sorted[2]
            elif len(dims) >= 2:
                # If we only have 2 dimensions, use them as length and width
                dims_sorted = sorted(dims, reverse=True)
                result["length_in"] = dims_sorted[0]
                result["width_in"] = dims_sorted[1]
            elif len(dims) >= 1:
                # If we only have 1 dimension, use it as length
                result["length_in"] = dims[0]
    
    print(f"[DEBUG] Final dimension extraction result: {result}")
    return result


def _extract_quantity(text: str) -> int:
    """
    Extract quantity from text. Looks for:
    - "Qty:", "Quantity:", "Q:", etc.
    - "x 10", "x10" patterns
    - Numbers near keywords like "parts", "pieces", "pcs"
    """
    t = text.lower()
    
    # Pattern 1: Explicit quantity labels
    qty_patterns = [
        r'\b(?:qty|quantity|q)\s*[=:]\s*(\d+)',
        r'\b(?:qty|quantity|q)\s+(\d+)',
        r'\b(\d+)\s*(?:parts?|pieces?|pcs?|units?)\b',
    ]
    
    for pattern in qty_patterns:
        matches = re.findall(pattern, t)
        if matches:
            return int(matches[0])
    
    # Pattern 2: "x 10" format
    x_pattern = r'\b[x×]\s*(\d+)\b'
    matches = re.findall(x_pattern, t)
    if matches:
        return int(matches[0])
    
    return 1  # Default


def _extract_weight(text: str) -> Optional[float]:
    """
    Extract weight from text. Looks for patterns like:
    - "Weight: 2.5 lbs" or "Weight: 2.5 lb"
    - "2.5 lbs" or "2.5 lb"
    """
    t = text.lower()
    
    weight_patterns = [
        r'\b(?:weight|wt)\s*[=:]\s*([\d.]+)\s*(?:lbs?|pounds?)',
        r'\b([\d.]+)\s*(?:lbs?|pounds?)\b',
    ]
    
    for pattern in weight_patterns:
        matches = re.findall(pattern, t)
        if matches:
            return float(matches[0])
    
    return None


def extract_signals(text: str) -> Dict[str, Any]:
    """
    Extract signals from PDF text including:
    - Material type
    - Dimensions (length, width, height)
    - Quantity
    - Weight (if available)
    """
    if not text:
        return {
            "material": None,
            "qty": 1,
            "raw_text_preview": "",
            "notes": "",
        }
    
    t = text.lower()
    signals = {}
    
    # Extract material
    material = None
    materials = ["aluminum", "aluminium", "stainless", "mild steel", "steel", "titanium", "brass", "copper"]
    for m in materials:
        if m in t:
            material = m
            break
    signals["material"] = material
    
    # Extract quantity
    signals["qty"] = _extract_quantity(text)
    
    # Extract dimensions
    print(f"[DEBUG] Calling _extract_dimensions with text length: {len(text) if text else 0}")
    dims = _extract_dimensions(text)
    print(f"[DEBUG] _extract_dimensions returned: {dims}")
    signals.update(dims)
    
    # Extract weight
    weight = _extract_weight(text)
    if weight is not None:
        signals["material_weight_lbs"] = weight
    
    # Extract machining time hints if present
    # Look for keywords like "complexity", "simple", "moderate", "complex"
    if any(word in t for word in ["complex", "difficult", "intricate"]):
        signals["complexity"] = "complex"
    elif any(word in t for word in ["simple", "basic", "easy"]):
        signals["complexity"] = "simple"
    else:
        signals["complexity"] = "moderate"
    
    # Extract size hints
    # Try to infer size from dimensions if available
    if signals.get("length_in") and signals.get("width_in") and signals.get("height_in"):
        avg_dim = (signals["length_in"] + signals["width_in"] + signals["height_in"]) / 3
        if avg_dim < 2:
            signals["size"] = "small"
        elif avg_dim > 6:
            signals["size"] = "large"
        else:
            signals["size"] = "medium"
    
    signals["raw_text_preview"] = text[:1200] if text else ""
    
    # Add debugging info about extraction
    extraction_debug = {
        "text_length": len(text) if text else 0,
        "has_dimensions": any(signals.get(d) is not None for d in ["length_in", "width_in", "height_in"]),
        "extracted_dims": {k: v for k, v in signals.items() if k in ["length_in", "width_in", "height_in"]}
    }
    signals["extraction_debug"] = extraction_debug
    signals["notes"] = f"Extracted from PDF: {len(text)} characters"
    
    return signals


def extract_signals_from_text(text: str) -> Dict[str, Any]:
    """
    Compatibility wrapper for main.py.

    main.py imports `extract_signals_from_text`, so we keep that name
    and delegate to `extract_signals`.
    """
    return extract_signals(text or "")


# ------------------------------------------------------------------------
# Core estimate logic
# ------------------------------------------------------------------------


def compute_estimate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase-2 estimating engine.

    - Fills in missing machining_minutes and material_weight_lbs using rules.
    - Applies multipliers for complexity, size, tolerance.
    - Returns either:
        { ready: False, missing_inputs: [...], ... }
      or
        { ready: True, cost_usd: ..., breakdown: {...}, ... }
    """
    # Normalize
    inputs = dict(inputs)  # copy
    inputs["material"] = _norm(inputs.get("material"))
    inputs["complexity"] = _norm(inputs.get("complexity")) or "moderate"
    inputs["size"] = _norm(inputs.get("size")) or "medium"
    inputs["tolerance"] = _norm(inputs.get("tolerance")) or "normal"

    qty = inputs.get("qty") or 1
    try:
        qty = int(qty)
    except Exception:
        qty = 1
    inputs["qty"] = qty

    missing: list[str] = []
    inferred: Dict[str, Any] = {}
    confidence = "high"

    # Material required (we don't estimate this)
    if not inputs["material"]:
        missing.append("material")

    # Try to infer machining_minutes
    mm = inputs.get("machining_minutes")
    if mm is None:
        mm = estimate_machining_minutes(inputs)
        if mm is not None:
            inputs["machining_minutes"] = mm
            inferred["machining_minutes"] = mm
            confidence = "medium"
        else:
            # Fallback: use moderate complexity default if estimation fails
            # This makes the field truly optional
            inputs["machining_minutes"] = 60  # Default moderate complexity base time
            inferred["machining_minutes"] = 60
            confidence = "low"
    else:
        inputs["machining_minutes"] = float(mm)

    # Try to infer material_weight_lbs
    wt = inputs.get("material_weight_lbs")
    if wt is None:
        wt = estimate_weight_lbs(inputs)
        if wt is not None:
            inputs["material_weight_lbs"] = wt
            inferred["material_weight_lbs"] = wt
            confidence = "medium"
        else:
            # If we can't estimate from dimensions, use a reasonable default based on size
            # This makes the field truly optional
            size = _norm(inputs.get("size")) or "medium"
            default_weights = {
                "small": 0.5,
                "medium": 2.0,
                "large": 5.0,
            }
            default_wt = default_weights.get(size, 2.0)
            inputs["material_weight_lbs"] = default_wt
            inferred["material_weight_lbs"] = default_wt
            confidence = "low"
    else:
        inputs["material_weight_lbs"] = float(wt)

    # If still missing key stuff, return "not ready"
    if missing or not inputs["material"]:
        return {
            "ready": False,
            "missing_inputs": missing,
            "message": "Need a few more details to generate a quote.",
            "confidence": confidence,
            "inferred": inferred,
        }

    # ---- Pricing math ---------------------------------------------------

    machining_minutes_each = float(inputs["machining_minutes"])
    material_weight_lbs_each = float(inputs["material_weight_lbs"])

    complexity_factor = {
        "simple": 1.0,
        "moderate": 1.15,
        "complex": 1.4,
    }.get(inputs["complexity"], 1.15)

    tolerance_factor = TOLERANCE_FACTOR.get(inputs["tolerance"], 1.0)

    # Machine rate adjusted for complexity / tolerance
    machine_rate = DEFAULT_MACHINE_RATE * complexity_factor * tolerance_factor

    # Material rate depends on material type a bit
    base_material_rate = 3.0
    mat = inputs["material"] or ""
    if "titanium" in mat:
        base_material_rate = 10.0
    elif "stainless" in mat:
        base_material_rate = 4.5

    machining_cost_each = machining_minutes_each * machine_rate
    material_cost_each = material_weight_lbs_each * base_material_rate

    subtotal_each = machining_cost_each + material_cost_each

    # Overall multiplier for overhead / profit
    overhead_multiplier = 1.25
    total_each = subtotal_each * overhead_multiplier
    total_all = total_each * qty

    # Simple lead time heuristic
    if machining_minutes_each <= 45:
        lead_time_days = 3
    elif machining_minutes_each <= 90:
        lead_time_days = 5
    else:
        lead_time_days = 7

    # If we inferred important things, lower confidence
    if inferred and confidence == "high":
        confidence = "medium"
    if "machining_minutes" in inferred and "material_weight_lbs" in inferred:
        confidence = "low"

    return {
        "ready": True,
        "cost_usd": round(total_all, 2),
        "lead_time_days": int(lead_time_days),
        "confidence": confidence,
        "inferred": inferred,
        "breakdown": {
            "qty": qty,
            "machining_minutes_each": round(machining_minutes_each, 2),
            "material_weight_lbs_each": round(material_weight_lbs_each, 2),
            "machine_rate_per_min": round(machine_rate, 2),
            "material_rate_per_lb": round(base_material_rate, 2),
            "machining_cost_each": round(machining_cost_each, 2),
            "material_cost_each": round(material_cost_each, 2),
            "subtotal_each": round(subtotal_each, 2),
            "multiplier": overhead_multiplier,
            "total_each": round(total_each, 2),
            "total_all": round(total_all, 2),
        },
    }
