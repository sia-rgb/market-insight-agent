const state = {
  payload: null,
  selectedDate: "",
  selectedSheet: "all",
  selectedClass: "all",
  selectedSeries: "",
  search: "",
};

const classLabels = {
  equity: "权益",
  fixed_income: "固收",
  fx: "外汇",
  commodity: "商品",
  derivative: "衍生品",
};

const globalIndexPerformanceConfig = {
  startDate: "2026-01-05",
  sourceSheet: "权益-全球股指",
  metricName: "最新收盘价",
  baselineValue: 100,
};

const els = {
  dataDate: document.querySelector("#dataDate"),
  generatedAt: document.querySelector("#generatedAt"),
  dateSelect: document.querySelector("#dateSelect"),
  sheetSelect: document.querySelector("#sheetSelect"),
  searchInput: document.querySelector("#searchInput"),
  classFilters: document.querySelector("#classFilters"),
  globalIndexList: document.querySelector("#globalIndexList"),
  globalIndexCanvas: document.querySelector("#globalIndexCanvas"),
  moverList: document.querySelector("#moverList"),
  metricGrid: document.querySelector("#metricGrid"),
  recordCount: document.querySelector("#recordCount"),
  detailRows: document.querySelector("#detailRows"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function formatNumber(value, digits = 2) {
  if (!isNumber(value)) return "--";
  const abs = Math.abs(value);
  const maxDigits = abs >= 1000 ? 2 : digits;
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: maxDigits,
    minimumFractionDigits: 0,
  }).format(value);
}

function formatInteger(value) {
  if (!isNumber(value)) return "--";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  }).format(value);
}

function unitText(unit) {
  const text = String(unit ?? "").trim();
  return text && text.toLowerCase() !== "raw" ? text : "";
}

function formatValue(value, unit) {
  const suffix = unitText(unit);
  return `${formatNumber(value, 4)}${suffix ? ` ${suffix}` : ""}`;
}

function formatPct(value) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}%`;
}

function formatRatioPct(value) {
  if (!isNumber(value)) return "--";
  return formatPct(value * 100);
}

function formatRatioPctPlain(value) {
  if (!isNumber(value)) return "--";
  return `${formatNumber(value * 100, 2)}%`;
}

function directionClass(record) {
  if (record.direction === "up") return "up";
  if (record.direction === "down") return "down";
  return "flat";
}

function directionMark(record) {
  if (record.direction === "up") return "▲";
  if (record.direction === "down") return "▼";
  return "■";
}

function signedClass(value) {
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function signedMark(value) {
  if (value > 0) return "▲";
  if (value < 0) return "▼";
  return "■";
}

function labelClass(value) {
  return classLabels[value] || value || "未分类";
}

function dateOffset(dateText, days) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText;
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function monthOffset(dateText, months) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText;
  date.setMonth(date.getMonth() + months);
  return date.toISOString().slice(0, 10);
}

function monthTicks(dates) {
  const byMonth = new Map();
  dates.forEach((date) => {
    const key = date.slice(0, 7);
    if (!byMonth.has(key)) byMonth.set(key, date);
  });
  return [...byMonth.entries()].map(([month, date], idx) => {
    const [, monthText] = month.split("-");
    return {
      date,
      label: `${Number(monthText)}月`,
    };
  });
}

function getRecordsForDate(date) {
  const payload = state.payload;
  if (!payload) return [];
  return payload.series.flatMap((series) => {
    const observation = series.observations.find((item) => item.date === date);
    if (!observation) return [];
    return [{
      date: observation.date,
      source_sheet: series.source_sheet,
      asset_class: series.asset_class,
      asset_name: series.asset_name,
      asset_key: series.asset_key,
      series_key: series.series_key,
      ticker: series.ticker,
      metric_name: series.metric_name,
      value: observation.value,
      unit: series.unit,
      previous_date: observation.previous_date,
      previous_value: observation.previous_value,
      daily_abs_change: observation.daily_abs_change,
      daily_pct_change: observation.daily_pct_change,
      direction: observation.direction,
    }];
  });
}

function globalIndexSeries() {
  return (state.payload?.series || []).filter((series) => series.source_sheet === "权益-全球股指");
}

function latestObservationBefore(series, date) {
  const observations = [...(series?.observations || [])]
    .filter((item) => item.date && item.date <= date && isNumber(item.value))
    .sort((a, b) => a.date.localeCompare(b.date));
  return observations.at(-1) || null;
}

function latestObservation(series) {
  const observations = [...(series?.observations || [])]
    .filter((item) => item.date && isNumber(item.value))
    .sort((a, b) => a.date.localeCompare(b.date));
  return observations.at(-1) || null;
}

function globalIndexRows() {
  const byAsset = new Map();
  globalIndexSeries().forEach((series) => {
    const key = series.asset_key || series.asset_name || series.series_key;
    if (!byAsset.has(key)) {
      byAsset.set(key, {
        asset_key: key,
        asset_name: series.asset_name,
        ticker: series.ticker,
        metrics: {},
      });
    }
    const observation = series.metric_name === "2026年至今"
      ? latestObservation(series)
      : latestObservationBefore(series, state.selectedDate);
    if (observation) {
      byAsset.get(key).metrics[series.metric_name] = {
        value: observation.value,
        date: observation.date,
        unit: series.unit,
      };
    }
  });

  return [...byAsset.values()]
    .filter((item) => item.metrics["最新收盘价"])
    .sort((a, b) => {
      const ay = a.metrics["最近一周"]?.value ?? -Infinity;
      const by = b.metrics["最近一周"]?.value ?? -Infinity;
      return by - ay;
    });
}

function renderGlobalIndexList() {
  const rows = globalIndexRows();
  if (!rows.length) {
    els.globalIndexList.innerHTML = '<div class="empty">暂无全球股指数据</div>';
    return;
  }

  els.globalIndexList.innerHTML = rows.map((row) => {
    const close = row.metrics["最新收盘价"]?.value;
    const week = row.metrics["最近一周"]?.value;
    const month = row.metrics["最近1月"]?.value;
    const ytd = row.metrics["2026年至今"]?.value;
    const title = `${row.asset_name || row.ticker}${isNumber(ytd) ? ` (${formatRatioPctPlain(ytd)})` : ""}`;
    const weekRecord = { direction: week > 0 ? "up" : week < 0 ? "down" : "flat" };
    const monthRecord = { direction: month > 0 ? "up" : month < 0 ? "down" : "flat" };
    const ytdRecord = { direction: ytd > 0 ? "up" : ytd < 0 ? "down" : "flat" };
    return `<div class="index-row">
      <div>
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(row.ticker || "")}</span>
        <div class="index-badges">
          <span class="change ${directionClass(weekRecord)}">周 ${escapeHtml(formatRatioPct(week))}</span>
          <span class="change ${directionClass(monthRecord)}">月 ${escapeHtml(formatRatioPct(month))}</span>
          <span class="change ${directionClass(ytdRecord)}">YTD ${escapeHtml(formatRatioPct(ytd))}</span>
        </div>
      </div>
      <div class="index-value">
        <strong>${escapeHtml(formatInteger(close))}</strong>
        <span>收盘价</span>
      </div>
    </div>`;
  }).join("");
}

function buildGlobalPerformanceSeries() {
  return (state.payload?.series || [])
    .filter((series) => (
      series.source_sheet === globalIndexPerformanceConfig.sourceSheet
      && series.metric_name === globalIndexPerformanceConfig.metricName
    ))
    .map((series) => {
      const observations = [...(series.observations || [])]
        .filter((item) => (
          item.date
          && item.date >= globalIndexPerformanceConfig.startDate
          && item.date <= state.selectedDate
          && isNumber(item.value)
        ))
        .sort((a, b) => a.date.localeCompare(b.date));
      const baselinePrice = observations[0]?.value;
      if (!isNumber(baselinePrice) || baselinePrice === 0) {
        return null;
      }
      const points = observations.map((item) => ({
        date: item.date,
        value: (item.value / baselinePrice) * globalIndexPerformanceConfig.baselineValue,
      }));
      return {
        name: series.asset_name || series.ticker,
        points,
      };
    })
    .filter(Boolean)
    .slice(0, 8);
}

function filteredRecords() {
  const query = state.search.trim().toLowerCase();
  return getRecordsForDate(state.selectedDate).filter((record) => {
    const classOk = state.selectedClass === "all" || record.asset_class === state.selectedClass;
    const sheetOk = state.selectedSheet === "all" || record.source_sheet === state.selectedSheet;
    const text = `${record.source_sheet} ${record.asset_name} ${record.metric_name} ${record.ticker}`.toLowerCase();
    const queryOk = !query || text.includes(query);
    return classOk && sheetOk && queryOk;
  });
}

function setStatus() {
  const payload = state.payload;
  els.dataDate.textContent = `数据日期 ${state.selectedDate || "--"}`;
  const generated = payload?.generated_at ? new Date(payload.generated_at) : null;
  els.generatedAt.textContent = generated && !Number.isNaN(generated.getTime())
    ? `生成时间 ${generated.toLocaleString("zh-CN", { hour12: false })}`
    : "生成时间 --";
}

function populateControls() {
  const payload = state.payload;
  const dates = [...(payload?.dates || [])].sort().reverse();
  els.dateSelect.innerHTML = dates.map((date) => (
    `<option value="${escapeHtml(date)}">${escapeHtml(date)}</option>`
  )).join("");
  els.dateSelect.value = state.selectedDate;

  const sheets = [...new Set((payload?.series || []).map((item) => item.source_sheet).filter(Boolean))].sort();
  els.sheetSelect.innerHTML = [
    '<option value="all">全部工作表</option>',
    ...sheets.map((sheet) => `<option value="${escapeHtml(sheet)}">${escapeHtml(sheet)}</option>`),
  ].join("");
  els.sheetSelect.value = state.selectedSheet;

  const classes = [...new Set((payload?.series || []).map((item) => item.asset_class).filter(Boolean))].sort();
  els.classFilters.innerHTML = [
    { value: "all", label: "全部" },
    ...classes.map((value) => ({ value, label: labelClass(value) })),
  ].map((item) => (
    `<button type="button" data-class="${escapeHtml(item.value)}" class="${state.selectedClass === item.value ? "active" : ""}">${escapeHtml(item.label)}</button>`
  )).join("");

  els.classFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedClass = button.dataset.class || "all";
      render();
    });
  });
}

function renderMovers(records) {
  const gainers = records
    .filter((item) => isNumber(item.daily_pct_change) && item.daily_pct_change > 0)
    .sort((a, b) => b.daily_pct_change - a.daily_pct_change)
    .slice(0, 5);
  const decliners = records
    .filter((item) => isNumber(item.daily_pct_change) && item.daily_pct_change < 0)
    .sort((a, b) => a.daily_pct_change - b.daily_pct_change)
    .slice(0, 5);

  const renderList = (items, emptyText) => {
    if (!items.length) return `<div class="empty mover-empty">${escapeHtml(emptyText)}</div>`;
    return items.map((record) => (
      `<div class="mover-item">
        <div>
          <strong>${escapeHtml(record.asset_name || record.source_sheet)}</strong>
          <span>${escapeHtml(record.metric_name)} · ${escapeHtml(record.source_sheet)}</span>
        </div>
        <div class="change ${signedClass(record.daily_pct_change)}">${signedMark(record.daily_pct_change)} ${formatPct(record.daily_pct_change)}</div>
      </div>`
    )).join("");
  };

  els.moverList.innerHTML = `
    <div class="mover-column">
      <div class="mover-column-head">
        <strong>日度涨幅榜 TOP5</strong>
        <span>正向涨幅</span>
      </div>
      ${renderList(gainers, "暂无正向涨幅指标")}
    </div>
    <div class="mover-column">
      <div class="mover-column-head">
        <strong>日度跌幅榜 TOP5</strong>
        <span>负向跌幅</span>
      </div>
      ${renderList(decliners, "暂无负向跌幅指标")}
    </div>`;
}

function renderMetricCards(records) {
  const visible = records
    .slice()
    .sort((a, b) => Math.abs(b.daily_pct_change || 0) - Math.abs(a.daily_pct_change || 0))
    .slice(0, 16);

  els.recordCount.textContent = `${records.length} 条`;
  if (!visible.length) {
    els.metricGrid.innerHTML = '<div class="empty">暂无匹配指标</div>';
    return;
  }

  if (!visible.some((item) => item.series_key === state.selectedSeries)) {
    state.selectedSeries = visible[0].series_key;
  }

  els.metricGrid.innerHTML = visible.map((record) => {
    const active = record.series_key === state.selectedSeries ? " active" : "";
    return `<button type="button" class="metric-card${active}" data-series="${escapeHtml(record.series_key)}">
      <span>${escapeHtml(record.source_sheet)}</span>
      <strong>${escapeHtml(record.asset_name || record.ticker || record.source_sheet)}</strong>
      <div class="value">${escapeHtml(formatValue(record.value, record.unit))}</div>
      <div class="metric-meta">
        <span>${escapeHtml(record.metric_name)}</span>
        <span class="change ${signedClass(record.daily_pct_change)}">${signedMark(record.daily_pct_change)} ${escapeHtml(formatPct(record.daily_pct_change))}</span>
      </div>
    </button>`;
  }).join("");

  els.metricGrid.querySelectorAll(".metric-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedSeries = card.dataset.series || "";
      render();
    });
  });
}

function renderTable(records) {
  const visible = records.slice(0, 120);
  els.detailRows.innerHTML = visible.map((record) => (
    `<tr>
      <td>${escapeHtml(record.source_sheet)}</td>
      <td>${escapeHtml(record.asset_name || record.ticker)}</td>
      <td>${escapeHtml(record.metric_name)}</td>
      <td class="numeric">${escapeHtml(formatValue(record.value, record.unit))}</td>
      <td class="numeric change ${signedClass(record.daily_abs_change)}">${escapeHtml(formatValue(record.daily_abs_change, record.unit))}</td>
      <td class="numeric change ${signedClass(record.daily_pct_change)}">${escapeHtml(formatPct(record.daily_pct_change))}</td>
    </tr>`
  )).join("");
}

function drawGlobalPerformanceChart() {
  const canvas = els.globalIndexCanvas;
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, rect.width) * ratio;
  canvas.height = Math.max(260, rect.height) * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = canvas.width / ratio;
  const height = canvas.height / ratio;
  const pad = { left: 58, right: 150, top: 24, bottom: 42 };
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#071421";
  ctx.fillRect(0, 0, width, height);

  const series = buildGlobalPerformanceSeries();
  const allPoints = series.flatMap((item) => item.points);
  if (!allPoints.length) {
    ctx.fillStyle = "#93a6bd";
    ctx.font = "13px Segoe UI";
    ctx.fillText("暂无全球股指表现数据", pad.left, height / 2);
    return;
  }

  const dates = [...new Set(allPoints.map((point) => point.date))].sort();
  const values = allPoints.map((point) => point.value);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  min = Math.floor(min / 5) * 5;
  max = Math.ceil(max / 5) * 5;

  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (date) => {
    const idx = dates.indexOf(date);
    return pad.left + (idx / Math.max(1, dates.length - 1)) * plotW;
  };
  const y = (value) => pad.top + ((max - value) / (max - min)) * plotH;

  ctx.strokeStyle = "rgba(147, 166, 189, 0.18)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#93a6bd";
  ctx.font = "12px Segoe UI";
  for (let i = 0; i <= 4; i += 1) {
    const yy = pad.top + (i / 4) * plotH;
    const label = max - ((max - min) * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillText(formatNumber(label, 1), 12, yy + 4);
  }

  monthTicks(dates).forEach((tick, idx, ticks) => {
    const xx = x(tick.date);
    ctx.textAlign = idx === 0 ? "left" : idx === ticks.length - 1 ? "right" : "center";
    ctx.fillText(tick.label, xx, height - 14);
  });
  ctx.textAlign = "left";

  const colors = ["#d8b766", "#46c5bb", "#55d58a", "#8aa8ff", "#f36d7a", "#f4a261", "#b8e986", "#c38fff"];
  const labels = [];
  series.forEach((item, idx) => {
    const color = colors[idx % colors.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.15;
    ctx.beginPath();
    item.points.forEach((point, pointIdx) => {
      const xx = x(point.date);
      const yy = y(point.value);
      if (pointIdx === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.stroke();

    const lastPoint = item.points.at(-1);
    if (lastPoint) {
      ctx.beginPath();
      ctx.arc(x(lastPoint.date), y(lastPoint.value), 2.4, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      labels.push({
        color,
        name: item.name,
        x: x(lastPoint.date),
        y: y(lastPoint.value),
      });
    }
  });

  labels.sort((a, b) => a.y - b.y);
  const minLabelGap = 16;
  labels.forEach((label, idx) => {
    const minY = idx === 0 ? pad.top + 4 : labels[idx - 1].labelY + minLabelGap;
    label.labelY = Math.max(label.y, minY);
  });
  for (let idx = labels.length - 1; idx >= 0; idx -= 1) {
    const maxY = idx === labels.length - 1 ? height - pad.bottom - 4 : labels[idx + 1].labelY - minLabelGap;
    labels[idx].labelY = Math.min(labels[idx].labelY, maxY);
  }

  ctx.font = "12px Segoe UI";
  labels.forEach((label) => {
    const labelX = width - pad.right + 16;
    ctx.strokeStyle = label.color;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(label.x + 4, label.y);
    ctx.lineTo(labelX - 6, label.labelY);
    ctx.stroke();

    ctx.fillStyle = label.color;
    ctx.fillText(label.name, labelX, label.labelY + 4);
  });
}

function render() {
  if (!state.payload) return;
  setStatus();
  populateControls();
  const records = filteredRecords();
  renderGlobalIndexList();
  drawGlobalPerformanceChart();
  renderMovers(records);
  renderMetricCards(records);
  renderTable(records);
}

async function init() {
  try {
    const response = await fetch("data/dashboard_data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    state.selectedDate = state.payload.latest_date || state.payload.dates?.at(-1) || "";
    populateControls();
    render();
  } catch (error) {
    els.moverList.innerHTML = `<div class="empty">数据加载失败：${escapeHtml(error.message)}</div>`;
    drawGlobalPerformanceChart();
  }
}

els.dateSelect.addEventListener("change", (event) => {
  state.selectedDate = event.target.value;
  render();
});

els.sheetSelect.addEventListener("change", (event) => {
  state.selectedSheet = event.target.value;
  render();
});

els.searchInput.addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});

window.addEventListener("resize", () => {
  drawGlobalPerformanceChart();
});

init();
