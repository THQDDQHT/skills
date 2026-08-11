function trimUrl(value) {
  return String(value || "").replace(/[.,;:!?，。、；：！？》）】)]+$/g, "");
}

export function normalizeSourceUrl(url) {
  try {
    const parsed = new URL(trimUrl(url));
    parsed.hash = "";
    parsed.hostname = parsed.hostname.toLowerCase();
    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.replace(/\/+$/g, "");
    }
    return parsed.toString();
  } catch {
    return String(url || "").trim();
  }
}

export function mergeSources(...sourceLists) {
  const seen = new Set();
  const merged = [];

  for (const sources of sourceLists) {
    for (const item of sources || []) {
      const url = typeof item?.url === "string" ? item.url.trim() : "";
      if (!url) continue;
      const key = normalizeSourceUrl(url);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push({ ...item, url });
    }
  }

  return merged;
}

function textField(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function sourceSnippet(source) {
  return textField(source?.snippet) || textField(source?.description) || textField(source?.content);
}

function clipText(value, maxChars) {
  const text = textField(value);
  if (!text) return "";
  const limit = Number.isFinite(maxChars) ? Math.max(0, maxChars) : text.length;
  if (limit <= 0) return "";
  return text.length > limit ? text.slice(0, limit).trimEnd() : text;
}

export function compactSource(source, { sourceChars = 400 } = {}) {
  const url = typeof source?.url === "string" ? trimUrl(source.url.trim()) : "";
  if (!url) return null;

  const out = {
    provider: textField(source.provider) || "unknown",
    url,
  };

  const title = textField(source.title);
  if (title) out.title = title;

  const sourceType = textField(source?.source_type);
  if (sourceType) out.source_type = sourceType;

  const tool = textField(source?.tool);
  if (tool) out.tool = tool;

  const snippet = clipText(sourceSnippet(source), sourceChars);
  if (snippet) out.snippet = snippet;

  if (Number.isFinite(source?.score)) out.score = source.score;

  const publishedDate = textField(source?.published_date);
  if (publishedDate) out.published_date = publishedDate;

  return out;
}

export function compactSources(sources, options = {}) {
  return (sources || []).map((source) => compactSource(source, options)).filter(Boolean);
}

function sourceRank(source) {
  const type = textField(source?.source_type);
  if (type === "citation") return 0;
  if (type === "searched") return 2;
  return 1;
}

export function selectSources(sources, { maxSources } = {}) {
  const list = sources || [];
  const total = list.length;
  const limit = Number.isFinite(maxSources) && maxSources > 0 ? maxSources : total;

  let items = list;
  if (total > limit) {
    items = list
      .map((source, index) => ({ source, index, rank: sourceRank(source) }))
      .sort((a, b) => a.rank - b.rank || a.index - b.index)
      .slice(0, limit)
      .sort((a, b) => a.index - b.index)
      .map((entry) => entry.source);
  }

  return { items, total, returned: items.length, omitted: total - items.length };
}

export function hasRawSourceValue(source, compacted = compactSource(source)) {
  if (!source || !compacted) return false;

  for (const [key, value] of Object.entries(source)) {
    if (value == null) continue;

    if (key === "provider" && textField(value) === compacted.provider) continue;
    if (key === "url" && trimUrl(String(value).trim()) === compacted.url) continue;
    if (key === "title" && textField(value) === compacted.title) continue;
    if (key === "source_type" && textField(value) === compacted.source_type) continue;
    if (key === "tool" && textField(value) === compacted.tool) continue;
    if (key === "score" && Number.isFinite(value) && value === compacted.score) continue;
    if (key === "published_date" && textField(value) === compacted.published_date) continue;

    if (key === "snippet" || key === "description" || key === "content") {
      const rawText = textField(value);
      if (!rawText) continue;
      if (compacted.snippet === rawText) continue;
      return true;
    }

    return true;
  }

  return false;
}

export function hasRawSourceValues(rawSources, compactedSources) {
  return (rawSources || []).some((source, index) => hasRawSourceValue(source, compactedSources?.[index]));
}

export function buildRawSourcesPayload({
  query,
  grok = [],
  extra = [],
  providerRaw = {},
  providerAttempts = [],
  grokToolCalls = [],
  createdAt = new Date().toISOString(),
} = {}) {
  const provider_raw = {};
  for (const [provider, raw] of Object.entries(providerRaw || {})) {
    if (raw !== undefined) provider_raw[provider] = raw;
  }

  return {
    query,
    grok,
    extra,
    provider_raw,
    provider_attempts: providerAttempts || [],
    ...(grokToolCalls?.length ? { grok_tool_calls: grokToolCalls } : {}),
    created_at: createdAt,
  };
}

