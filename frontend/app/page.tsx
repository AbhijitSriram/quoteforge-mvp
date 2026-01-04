"use client";

import { useMemo, useState } from "react";

type AskResult = {
  source: string;
  page: number;
  chunk_index: number;
  preview?: string;
  text?: string;
};

type QuoteReference = {
  source: string;
  page: number;
  chunk_index: number;
  text?: string;
};

type QuoteEstimate =
  | {
      ready: false;
      missing_inputs: string[];
      message?: string;
    }
  | {
      ready: true;
      cost_usd: number;
      lead_time_days: number;
      breakdown?: Record<string, any>;
    };

type QuoteResponse = {
  quote_id?: string;
  uploaded_file?: string;
  signals?: Record<string, any>;
  references?: QuoteReference[];
  estimate?: QuoteEstimate;
  next_step?: string;
  result_count?: number;
  db_path?: string;
};

export default function Home() {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  const [mode, setMode] = useState<"QUOTE" | "ASK">("QUOTE");

  // ---------------- ASK MODE ----------------
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [askLoading, setAskLoading] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [askResults, setAskResults] = useState<AskResult[]>([]);

  // ---------------- QUOTE MODE ----------------
  const [file, setFile] = useState<File | null>(null);

  // ✅ Required at upload
  const [material, setMaterial] = useState("aluminum");
  const [qty, setQty] = useState(1);

  // Optional overrides (to guarantee first-go quote)
  const [machiningMinutes, setMachiningMinutes] = useState<string>("");
  const [materialWeight, setMaterialWeight] = useState<string>("");

  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const [quoteId, setQuoteId] = useState<string | null>(null);
  const [quoteData, setQuoteData] = useState<QuoteResponse | null>(null);

  // If your backend still returns missing_inputs, we show them
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const missingInputs = useMemo(() => {
    const est = quoteData?.estimate;
    if (est && "ready" in est && est.ready === false) return est.missing_inputs || [];
    return [];
  }, [quoteData]);

  async function onAsk() {
    setAskLoading(true);
    setAskError(null);
    setAskResults([]);

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: topK }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error ${res.status}: ${text}`);
      }

      const data = await res.json();
      setAskResults(data.results || []);
    } catch (e: any) {
      setAskError(e?.message || "Unknown error");
    } finally {
      setAskLoading(false);
    }
  }

  async function onUploadAndQuote() {
    setQuoteLoading(true);
    setQuoteError(null);
    setQuoteData(null);
    setQuoteId(null);
    setAnswers({});

    try {
      if (!file) throw new Error("Please choose a file to upload.");
      if (!material.trim()) throw new Error("Material is required.");

      const form = new FormData();
      form.append("file", file);
      form.append("material", material);
      form.append("qty", String(qty));

      // optional overrides
      if (machiningMinutes.trim()) form.append("machining_minutes", machiningMinutes.trim());
      if (materialWeight.trim()) form.append("material_weight_lbs", materialWeight.trim());

      const res = await fetch(`${API_BASE}/quote`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error ${res.status}: ${text}`);
      }

      const data: QuoteResponse = await res.json();
      setQuoteData(data);
      if (data.quote_id) setQuoteId(data.quote_id);
    } catch (e: any) {
      setQuoteError(e?.message || "Unknown error");
    } finally {
      setQuoteLoading(false);
    }
  }

  // Optional: If you still have a backend answer endpoint (only use if it exists)
  async function onSubmitAnswersIfSupported() {
    setQuoteLoading(true);
    setQuoteError(null);

    try {
      if (!quoteId) throw new Error("Missing quote_id (upload again).");

      const payload: Record<string, any> = {};
      for (const k of missingInputs) {
        const v = answers[k];
        if (v !== undefined && String(v).trim() !== "") payload[k] = v;
      }

      // If you did NOT implement this endpoint, remove this button section.
      const res = await fetch(`${API_BASE}/quote/${quoteId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error ${res.status}: ${text}`);
      }

      const data: QuoteResponse = await res.json();
      setQuoteData(data);
    } catch (e: any) {
      setQuoteError(e?.message || "Unknown error");
    } finally {
      setQuoteLoading(false);
    }
  }

  function resetQuote() {
    setFile(null);
    setMaterial("aluminum");
    setQty(1);
    setMachiningMinutes("");
    setMaterialWeight("");
    setQuoteId(null);
    setQuoteData(null);
    setQuoteError(null);
    setAnswers({});
  }

  const isCadOrPdfOrImage =
    file?.name?.toLowerCase().endsWith(".pdf") ||
    file?.name?.toLowerCase().endsWith(".step") ||
    file?.name?.toLowerCase().endsWith(".stp") ||
    file?.name?.toLowerCase().match(/\.(png|jpg|jpeg)$/);

  return (
    <main
      style={{
        maxWidth: 980,
        margin: "40px auto",
        padding: 20,
        fontFamily: "Arial, sans-serif",
        color: "#fff",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 30, margin: 0 }}>QuoteForge MVP</h1>
          <p style={{ marginTop: 8, opacity: 0.8 }}>
            Upload a drawing/CAD → get an estimated cost + lead time and see supporting doc references.
          </p>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => setMode("QUOTE")}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: "1px solid #333",
              background: mode === "QUOTE" ? "#2d7ff9" : "#111",
              color: "#fff",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            Quote
          </button>
          <button
            onClick={() => setMode("ASK")}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: "1px solid #333",
              background: mode === "ASK" ? "#2d7ff9" : "#111",
              color: "#fff",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            Search Docs
          </button>
        </div>
      </div>

      {/* ---------------- QUOTE MODE ---------------- */}
      {mode === "QUOTE" && (
        <>
          <section
            style={{
              marginTop: 22,
              padding: 16,
              border: "1px solid #333",
              borderRadius: 14,
              background: "#0b0b0b",
            }}
          >
            <h2 style={{ fontSize: 18, marginTop: 0 }}>1) Upload a drawing / CAD</h2>

            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="file"
                // ✅ allow PDF + CAD + images (backend currently supports multipart upload; STEP/STP best for auto)
                accept=".pdf,.step,.stp,image/png,image/jpeg"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                style={{
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid #333",
                  background: "#111",
                  color: "#fff",
                  width: 420,
                }}
              />

              <button
                onClick={onUploadAndQuote}
                disabled={quoteLoading || !file || !material.trim()}
                style={{
                  padding: "12px 16px",
                  borderRadius: 10,
                  border: "none",
                  background: quoteLoading ? "#555" : "#2d7ff9",
                  color: "#fff",
                  cursor: quoteLoading ? "not-allowed" : "pointer",
                  fontWeight: 800,
                }}
              >
                {quoteLoading ? "Processing..." : "Upload & Quote"}
              </button>

              <button
                onClick={resetQuote}
                disabled={quoteLoading}
                style={{
                  padding: "12px 14px",
                  borderRadius: 10,
                  border: "1px solid #333",
                  background: "#111",
                  color: "#fff",
                  cursor: quoteLoading ? "not-allowed" : "pointer",
                  fontWeight: 700,
                }}
              >
                Reset
              </button>
            </div>

            {/* Material/QTY/optional overrides */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 13, opacity: 0.85 }}>Material (required)</label>
                <select
                  value={material}
                  onChange={(e) => setMaterial(e.target.value)}
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff",
                    width: 220,
                  }}
                >
                  <option value="aluminum">Aluminum</option>
                  <option value="stainless">Stainless</option>
                  <option value="mild steel">Mild Steel</option>
                  <option value="steel">Steel</option>
                  <option value="titanium">Titanium</option>
                </select>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 13, opacity: 0.85 }}>Qty</label>
                <input
                  type="number"
                  min={1}
                  value={qty}
                  onChange={(e) => setQty(Number(e.target.value))}
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff",
                    width: 120,
                  }}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 13, opacity: 0.85 }}>Machining Minutes (optional)</label>
                <input
                  value={machiningMinutes}
                  onChange={(e) => setMachiningMinutes(e.target.value)}
                  placeholder="e.g., 45"
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff",
                    width: 220,
                  }}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 13, opacity: 0.85 }}>Material Weight (lbs) (optional)</label>
                <input
                  value={materialWeight}
                  onChange={(e) => setMaterialWeight(e.target.value)}
                  placeholder="e.g., 2.5"
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff",
                    width: 220,
                  }}
                />
              </div>
            </div>

            <div style={{ marginTop: 10, opacity: 0.75, fontSize: 13 }}>
              Backend: <code style={{ color: "#ddd" }}>{API_BASE}</code>
              {file && (
                <>
                  {" "}
                  • File: <code style={{ color: "#ddd" }}>{file.name}</code>
                  {!isCadOrPdfOrImage && (
                    <span style={{ color: "#ffb3b3" }}> (unsupported extension)</span>
                  )}
                </>
              )}
            </div>

            {quoteError && (
              <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: "#3b1b1b", color: "#ffb3b3" }}>
                {quoteError}
              </div>
            )}
          </section>

          {quoteData && (
            <section
              style={{
                marginTop: 18,
                padding: 16,
                border: "1px solid #333",
                borderRadius: 14,
                background: "#0b0b0b",
              }}
            >
              <h2 style={{ fontSize: 18, marginTop: 0 }}>2) Quote result</h2>

              <div style={{ fontSize: 13, opacity: 0.85 }}>
                <div>
                  <b>quote_id:</b> {quoteData.quote_id || quoteId || "(none)"}
                </div>
                {quoteData.uploaded_file && (
                  <div>
                    <b>uploaded_file:</b> {quoteData.uploaded_file}
                  </div>
                )}
                {quoteData.next_step && (
                  <div>
                    <b>next_step:</b> {quoteData.next_step}
                  </div>
                )}
              </div>

              {quoteData.signals && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ fontWeight: 800, marginBottom: 8 }}>Extracted signals</div>
                  <pre
                    style={{
                      margin: 0,
                      padding: 14,
                      borderRadius: 12,
                      border: "1px solid #333",
                      background: "#111",
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {JSON.stringify(quoteData.signals, null, 2)}
                  </pre>
                </div>
              )}

              {/* If estimate ready */}
              {quoteData.estimate && "ready" in quoteData.estimate && quoteData.estimate.ready === true && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontWeight: 900, fontSize: 18 }}>✅ Quote Ready</div>

                  <div style={{ display: "flex", gap: 18, marginTop: 10, flexWrap: "wrap" }}>
                    <div style={{ padding: 14, border: "1px solid #333", borderRadius: 12, background: "#111", minWidth: 220 }}>
                      <div style={{ opacity: 0.8, fontSize: 13 }}>Estimated Cost</div>
                      <div style={{ fontSize: 22, fontWeight: 900 }}>${quoteData.estimate.cost_usd}</div>
                    </div>

                    <div style={{ padding: 14, border: "1px solid #333", borderRadius: 12, background: "#111", minWidth: 220 }}>
                      <div style={{ opacity: 0.8, fontSize: 13 }}>Lead Time</div>
                      <div style={{ fontSize: 22, fontWeight: 900 }}>{quoteData.estimate.lead_time_days} days</div>
                    </div>
                  </div>

                  {quoteData.estimate.breakdown && (
                    <div style={{ marginTop: 14 }}>
                      <div style={{ fontWeight: 800, marginBottom: 8 }}>Breakdown</div>
                      <pre
                        style={{
                          margin: 0,
                          padding: 14,
                          borderRadius: 12,
                          border: "1px solid #333",
                          background: "#111",
                          overflowX: "auto",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {JSON.stringify(quoteData.estimate.breakdown, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* If estimate not ready */}
              {quoteData.estimate && "ready" in quoteData.estimate && quoteData.estimate.ready === false && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontWeight: 900, fontSize: 16 }}>⚠️ Missing inputs ({missingInputs.length})</div>
                  <div style={{ opacity: 0.8, marginTop: 6 }}>
                    {quoteData.estimate.message || "Please provide these values to finish the quote."}
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
                    {missingInputs.map((k) => (
                      <div key={k} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <label style={{ fontSize: 13, opacity: 0.85 }}>{k}</label>
                        <input
                          value={answers[k] ?? ""}
                          onChange={(e) => setAnswers((prev) => ({ ...prev, [k]: e.target.value }))}
                          placeholder={k === "machining_minutes" ? "e.g., 45" : k === "material_weight_lbs" ? "e.g., 2.5" : "Enter value"}
                          style={{
                            padding: 12,
                            borderRadius: 10,
                            border: "1px solid #333",
                            background: "#111",
                            color: "#fff",
                          }}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Only useful if you implemented /quote/{quote_id}/answer */}
                  <button
                    onClick={onSubmitAnswersIfSupported}
                    disabled={quoteLoading}
                    style={{
                      marginTop: 14,
                      padding: "12px 16px",
                      borderRadius: 10,
                      border: "none",
                      background: quoteLoading ? "#555" : "#2d7ff9",
                      color: "#fff",
                      cursor: quoteLoading ? "not-allowed" : "pointer",
                      fontWeight: 800,
                    }}
                  >
                    {quoteLoading ? "Submitting..." : "Submit & Recalculate (if supported)"}
                  </button>

                  <div style={{ marginTop: 10, opacity: 0.75, fontSize: 13 }}>
                    Tip: To get a full quote in the first go, provide <b>Machining Minutes</b> and <b>Material Weight</b> before clicking Upload.
                  </div>
                </div>
              )}

              {/* References */}
              {quoteData.references && quoteData.references.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <div style={{ fontWeight: 800, marginBottom: 8 }}>References from indexed docs</div>

                  {quoteData.references.map((r, idx) => (
                    <div
                      key={idx}
                      style={{
                        marginTop: 10,
                        padding: 14,
                        borderRadius: 12,
                        border: "1px solid #333",
                        background: "#111",
                      }}
                    >
                      <div style={{ fontSize: 13, opacity: 0.85 }}>
                        <b>{r.source}</b> • page {r.page} • chunk {r.chunk_index}
                      </div>
                      {r.text && (
                        <div style={{ marginTop: 10, whiteSpace: "pre-wrap", lineHeight: 1.4, opacity: 0.95 }}>
                          {r.text}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {/* ---------------- ASK MODE ---------------- */}
      {mode === "ASK" && (
        <>
          <section style={{ marginTop: 22, padding: 16, border: "1px solid #333", borderRadius: 14, background: "#0b0b0b" }}>
            <h2 style={{ fontSize: 18, marginTop: 0 }}>Search the indexed docs</h2>

            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask something... (e.g., Upload a drawing)"
                style={{
                  flex: 1,
                  padding: 12,
                  borderRadius: 10,
                  border: "1px solid #333",
                  background: "#111",
                  color: "#fff",
                }}
              />
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                style={{
                  width: 90,
                  padding: 12,
                  borderRadius: 10,
                  border: "1px solid #333",
                  background: "#111",
                  color: "#fff",
                }}
                title="Top K"
              />
              <button
                onClick={onAsk}
                disabled={askLoading || !question.trim()}
                style={{
                  padding: "12px 16px",
                  borderRadius: 10,
                  border: "none",
                  background: askLoading ? "#555" : "#2d7ff9",
                  color: "#fff",
                  cursor: askLoading ? "not-allowed" : "pointer",
                  fontWeight: 800,
                }}
              >
                {askLoading ? "Searching..." : "Ask"}
              </button>
            </div>

            {askError && (
              <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: "#3b1b1b", color: "#ffb3b3" }}>
                {askError}
              </div>
            )}
          </section>

          <section style={{ marginTop: 18 }}>
            <h2 style={{ fontSize: 18 }}>Results ({askResults.length})</h2>

            {askResults.length === 0 && !askLoading && <div style={{ opacity: 0.7 }}>No results yet.</div>}

            {askResults.map((r, idx) => (
              <div
                key={idx}
                style={{
                  marginTop: 12,
                  padding: 14,
                  borderRadius: 12,
                  border: "1px solid #333",
                  background: "#0b0b0b",
                  color: "#fff",
                }}
              >
                <div style={{ fontSize: 13, opacity: 0.85 }}>
                  <b>{r.source}</b> • page {r.page} • chunk {r.chunk_index}
                </div>
                <div style={{ marginTop: 10, whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
                  {r.preview || r.text || ""}
                </div>
              </div>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
