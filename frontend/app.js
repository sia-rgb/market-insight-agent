const state = {
  payload: null,
  selectedDate: "",
  selectedClass: "all",
};

const classLabels = {
  equity: "权益",
  fixed_income: "固收",
  fx: "外汇",
  commodity: "商品",
  derivative: "衍生品",
};

const classOrder = ["equity", "fixed_income", "derivative", "fx", "commodity"];

const metricLabels = {
  close: "close（最新收盘价）",
  EDBclose: "EDBclose（最新收盘价）",
  daily_call_volume: "daily_call_volume（认购期权成交量，赌价格上涨）",
  daily_volume: "daily_volume（期权全部合约总成交量，代表整体活跃度）",
  daily_put_volume: "daily_put_volume（认沽期权成交量，赌价格下跌）",
  daily_contract_rate: "daily_contract_rate（期权合约换手率，反映市场短期博弈热度）",
  daily_call_position: "daily_call_position（认购期权持仓量，反映市场中长期多头预期）",
  daily_put_position: "daily_put_position（认沽期权持仓量，反映市场中长期空头预期）",
  daily_position: "daily_position（期权全部合约总持仓量，反映市场中长期配置与对冲总需求）",
  "USDCNY.EX": "USDCNY.EX（美元兑人民币汇率）",
  "USDX.FX": "USDX.FX（美元对一篮子主要货币的加权平均汇率）",
  smallBillInflowMoney: "smallBillInflowMoney（单笔成交4万元以下的净流入）",
  middleBillInflowMoney: "middleBillInflowMoney（单笔成交4–20万元的净流入）",
  largeBillInflowMoney: "largeBillInflowMoney（单笔成交 20 万元以上的净流入）",
};

const globalIndexPerformanceConfig = {
  startDate: "2026-01-05",
  sourceSheet: "权益-全球股指",
  metricName: "最新收盘价",
  baselineValue: 100,
};

const globalIndexSourceSheet = "权益-全球股指";

const els = {
  dateSelect: document.querySelector("#dateSelect"),
  classFilters: document.querySelector("#classFilters"),
  globalIndexList: document.querySelector("#globalIndexList"),
  globalIndexCanvas: document.querySelector("#globalIndexCanvas"),
  vixCanvas: document.querySelector("#vixCanvas"),
  treasuryCanvas: document.querySelector("#treasuryCanvas"),
  moverList: document.querySelector("#moverList"),
  detailRows: document.querySelector("#detailRows"),
  exportLongImage: document.querySelector("#exportLongImage"),
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

function formatSignedValue(value, unit) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  const suffix = unitText(unit);
  return `${sign}${formatNumber(value, 4)}${suffix ? ` ${suffix}` : ""}`;
}

function formatPct(value) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}%`;
}

function formatPctFixed(value, digits = 2) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumberFixed(value, digits)}%`;
}

function formatRatioPct(value) {
  if (!isNumber(value)) return "--";
  return formatPct(value * 100);
}

function formatRatioPctFixed(value, digits = 2) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumberFixed(value * 100, digits)}%`;
}

function formatRatioPctPlain(value) {
  if (!isNumber(value)) return "--";
  return `${formatNumber(value * 100, 2)}%`;
}

function formatNumberFixed(value, digits = 2) {
  if (!isNumber(value)) return "--";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatSignedValueFixed(value, unit, digits = 2) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  const suffix = unitText(unit);
  return `${sign}${formatNumberFixed(value, digits)}${suffix ? ` ${suffix}` : ""}`;
}

function formatValueFixed(value, unit, digits = 2) {
  const suffix = unitText(unit);
  return `${formatNumberFixed(value, digits)}${suffix ? ` ${suffix}` : ""}`;
}

function isOptionLotMetric(record) {
  return record?.source_sheet === "衍生品-50ETF期权" && [
    "daily_volume",
    "daily_call_position",
    "daily_call_volume",
    "daily_position",
    "daily_put_position",
    "daily_put_volume",
  ].includes(record.metric_name);
}

function formatOptionLotValue(value) {
  if (!isNumber(value)) return "--";
  return `${formatNumberFixed(value / 10000, 2)}万张`;
}

function isMarginBalanceMetric(record) {
  return record?.source_sheet === "权益-两融余额" && [
    "两融交易额",
    "融券余额",
    "融资买入额",
    "融资余额",
    "融资卖出额",
    "融资融券余额(沪深两市)",
  ].includes(record.metric_name);
}

function formatMarginBalanceValue(value) {
  if (!isNumber(value)) return "--";
  return `${formatNumberFixed(value / 100000000, 2)}亿元`;
}

function formatMarginBalanceChange(value) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumberFixed(value / 100000000, 2)}亿元`;
}

function isRetailFlowMetric(record) {
  return record?.source_sheet === "权益-散户情绪资金流向" && [
    "smallBillInflowMoney",
    "middleBillInflowMoney",
    "largeBillInflowMoney",
  ].includes(record.metric_name);
}

function hasFlowChangeStatus(record) {
  return Boolean(record?.flow_change_type || record?.flow_display_text || record?.flow_direction || record?.flow_severity_hint);
}

function formatRetailFlowValue(value) {
  if (!isNumber(value)) return "--";
  return `${formatNumberFixed(value / 10000, 2)}亿元`;
}

function formatRetailFlowChange(value) {
  if (!isNumber(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumberFixed(value / 10000, 2)}亿元`;
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

function severityClass(record) {
  if (record?.flow_severity_hint === "positive") return "up";
  if (record?.flow_severity_hint === "negative") return "down";
  if (record?.flow_severity_hint === "neutral") return "flat";
  return signedClass(record?.daily_pct_change);
}

function severityMark(record) {
  if (record?.flow_severity_hint === "positive") return "▲";
  if (record?.flow_severity_hint === "negative") return "▼";
  return signedMark(record?.daily_pct_change);
}

function labelClass(value) {
  return classLabels[value] || value || "未分类";
}

function labelMetric(value) {
  return metricLabels[value] || value || "";
}

function labelMetricBrief(value) {
  const text = labelMetric(value);
  if ([
    "daily_call_volume",
    "daily_volume",
    "daily_put_volume",
    "daily_contract_rate",
    "smallBillInflowMoney",
    "middleBillInflowMoney",
    "largeBillInflowMoney",
  ].includes(value)) {
    return text;
  }
  return text.replace(/\s*[（(][^（）()]*[）)]\s*$/, "");
}

function labelMetricDetail(value) {
  if ([
    "A股总成交额（亿元）",
    "两融交易额占A股成交额(%)",
    "南向-成交净买入(亿元,港元)",
  ].includes(value)) {
    return String(value || "").replace(/\s*[（(][^（）()]*[）)]\s*$/, "");
  }
  return labelMetric(value);
}

function splitMetricDetailText(record) {
  const raw = labelMetricDetailRecord(record);
  const ticker = String(record?.ticker || "").trim();
  if (ticker === "USDCNY.EX" && record?.metric_name === "close") {
    return { main: raw, note: "美元兑人民币汇率" };
  }
  if (ticker === "USDX.FX" && record?.metric_name === "close") {
    return { main: raw, note: "美元对一篮子主要货币的加权平均汇率" };
  }
  const groupedSheets = new Set(["权益-散户情绪资金流向", "衍生品-50ETF期权"]);
  if (!groupedSheets.has(record?.source_sheet)) {
    return { main: raw, note: "" };
  }
  const text = String(raw || "").trim();
  const match = text.match(/^(.*?)[（(]([^（）()]*)[）)]$/);
  if (!match) {
    return { main: text, note: "" };
  }
  return {
    main: match[1].trim(),
    note: match[2].trim(),
  };
}

const detailGroupOrder = ["权益", "资金面", "固收", "衍生品", "外汇", "商品"];

function detailGroupLabel(record) {
  const sheet = String(record?.source_sheet || "").trim();
  if (sheet === "权益-VIX") return "权益";
  if (["权益-A股交易量", "权益-两融余额", "权益-散户情绪资金流向", "权益-南北向"].includes(sheet)) return "资金面";
  if (sheet.startsWith("外汇-")) return "外汇";
  if (sheet.startsWith("衍生品-")) return "衍生品";
  if (sheet.startsWith("固收-")) return "固收";
  if (sheet.startsWith("大宗商品-")) return "商品";
  return "其他";
}

function renderNumericHtml(text) {
  const raw = String(text ?? "");
  const match = raw.match(/^([+-]?[\d,]+(?:\.\d+)?)(?:\s*(.+))?$/);
  if (!match) return escapeHtml(raw);
  const main = match[1];
  const unit = (match[2] || "").trim();
  return `<span class="numeric-wrap"><span class="numeric-main">${escapeHtml(main)}</span>${unit ? `<span class="numeric-unit">${escapeHtml(unit)}</span>` : ""}</span>`;
}

function labelMetricDetailRecord(record) {
  const ticker = String(record.ticker || "").trim();
  if ((ticker === "USDCNY.EX" || ticker === "USDX.FX") && record?.metric_name === "close") {
    return labelMetric("close");
  }
  return labelMetricDetail(record.metric_name);
}

function labelAssetDetail(record) {
  const ticker = String(record.ticker || "").trim();
  if (ticker === "USDCNY.EX") return "USDCNY.EX（美元兑人民币汇率）";
  if (ticker === "USDX.FX") return "USDX.FX（美元指数）";
  return record.asset_name || record.ticker || "";
}

function titleAssetName(record) {
  const raw = String(record.asset_name || record.source_sheet || "").trim();
  const ticker = String(record.ticker || "").trim();
  if (!raw) return ticker;
  const parts = raw.split("|").map((part) => part.trim()).filter(Boolean);
  if (parts.length > 1 && ticker && parts[0] === ticker) {
    return parts.slice(1).join(" | ");
  }
  return raw;
}

function titleLine(record) {
  const ticker = String(record.ticker || "").trim();
  const asset = titleAssetName(record);
  if (ticker && asset) return `${ticker} | ${asset}`;
  return ticker || asset;
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

function formatDisplayDate(dateText) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateText || "--";
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

function todayDateString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(new Date());
}

function previousAvailableDate(date) {
  const dates = allObservationDates()
    .filter((item) => item && item <= date)
    .sort();
  return dates.at(-1) || date;
}

function effectiveCloseDate() {
  return state.selectedDate || latestTradingDateOnOrBefore(state.payload?.latest_date || todayDateString());
}

function tradingDates() {
  return [...new Set(allSeries()
    .filter((series) => (
      series.source_sheet === globalIndexSourceSheet
      && series.metric_name === globalIndexPerformanceConfig.metricName
    ))
    .flatMap((series) => series.observations || [])
    .map((item) => item.date)
    .filter((date) => date && isWeekdayDate(date)))].sort();
}

function latestTradingDateOnOrBefore(dateText) {
  const dates = tradingDates().filter((date) => date <= dateText);
  return dates.at(-1) || previousAvailableDate(dateText);
}

function allSeries() {
  return state.payload?.series_all || state.payload?.series || [];
}

function allObservationDates() {
  return [...new Set(allSeries().flatMap((series) => (
    series.observations || []
  ).map((item) => item.date).filter(Boolean)))];
}

function isWeekdayDate(dateText) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return false;
  const day = date.getDay();
  return day !== 0 && day !== 6;
}

function isGlobalIndexSeries(series) {
  return series?.source_sheet === globalIndexSourceSheet;
}

function recordDateForSeries(series) {
  return effectiveCloseDate();
}

function getRecordsForDate(date) {
  if (!state.payload) return [];
  return allSeries().flatMap((series) => {
    const targetDate = date || recordDateForSeries(series);
    const observation = latestObservationBefore(series, targetDate);
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
      flow_change_type: observation.flow_change_type,
      flow_display_text: observation.flow_display_text,
      flow_direction: observation.flow_direction,
      flow_severity_hint: observation.flow_severity_hint,
    }];
  });
}

function globalIndexSeries() {
  return allSeries().filter((series) => isGlobalIndexSeries(series));
}

function canonicalGlobalIndexMetric(metricName) {
  const aliases = {
    "周变动": "最近一周",
    "月变动": "最近1月",
    "YTD变动": "2026年至今",
    "YTD至今": "2026年至今",
    "年初至今": "2026年至今",
  };
  return aliases[metricName] || metricName;
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
  const referenceDate = effectiveCloseDate();
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
    const observation = latestObservationBefore(series, referenceDate);
    if (observation) {
      byAsset.get(key).metrics[canonicalGlobalIndexMetric(series.metric_name)] = {
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

  const header = `<div class="index-row index-head">
    <div class="index-name"><strong>指数名称</strong></div>
    <div class="index-metric"><span>最新收盘价</span></div>
    <div class="index-metric"><span>周变动</span></div>
    <div class="index-metric"><span>月变动</span></div>
    <div class="index-metric"><span>YTD变动</span></div>
  </div>`;

  els.globalIndexList.innerHTML = header + rows.map((row) => {
    const close = row.metrics["最新收盘价"]?.value;
    const week = row.metrics["最近一周"]?.value;
    const month = row.metrics["最近1月"]?.value;
    const ytd = row.metrics["2026年至今"]?.value;
    const weekRecord = { direction: week > 0 ? "up" : week < 0 ? "down" : "flat" };
    const monthRecord = { direction: month > 0 ? "up" : month < 0 ? "down" : "flat" };
    const ytdRecord = { direction: ytd > 0 ? "up" : ytd < 0 ? "down" : "flat" };
    return `<div class="index-row">
      <div class="index-name">
        <strong>${escapeHtml(row.asset_name || row.ticker || "")}</strong>
      </div>
      <div class="index-metric index-value-cell">
        <strong>${escapeHtml(formatInteger(close))}</strong>
      </div>
      <div class="index-metric index-value-cell change ${directionClass(weekRecord)}">
        <strong>${escapeHtml(formatRatioPctFixed(week, 2))}</strong>
      </div>
      <div class="index-metric index-value-cell change ${directionClass(monthRecord)}">
        <strong>${escapeHtml(formatRatioPctFixed(month, 2))}</strong>
      </div>
      <div class="index-metric index-value-cell change ${directionClass(ytdRecord)}">
        <strong>${escapeHtml(formatRatioPctFixed(ytd, 2))}</strong>
      </div>
    </div>`;
  }).join("");
}

function buildGlobalPerformanceSeries() {
  return allSeries()
    .filter((series) => (
      series.source_sheet === globalIndexPerformanceConfig.sourceSheet
      && series.metric_name === globalIndexPerformanceConfig.metricName
    ))
    .map((series) => {
      const observations = [...(series.observations || [])]
        .filter((item) => (
          item.date
          && item.date >= globalIndexPerformanceConfig.startDate
          && item.date <= effectiveCloseDate()
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
    .slice(0, 9);
}

function vixSeries() {
  return allSeries().find((series) => (
    series.source_sheet === "权益-VIX"
    && series.metric_name === "close"
  )) || null;
}

function vixPoints() {
  return [...(vixSeries()?.observations || [])]
    .filter((item) => (
      item.date
      && item.date >= "2026-01-01"
      && item.date <= effectiveCloseDate()
      && isNumber(item.value)
    ))
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((item) => ({ date: item.date, value: item.value }));
}

function treasurySeries() {
  return allSeries().find((series) => (
    series.source_sheet === "固收-债券收益率"
    && series.asset_name === "美国:国债收益率:10年"
    && series.metric_name === "EDBclose"
  )) || null;
}

function treasuryPoints() {
  return [...(treasurySeries()?.observations || [])]
    .filter((item) => (
      item.date
      && item.date >= "2026-01-01"
      && item.date <= effectiveCloseDate()
      && isNumber(item.value)
    ))
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((item) => ({ date: item.date, value: item.value }));
}

function filteredRecords() {
  return getRecordsForDate().filter((record) => {
    const classOk = state.selectedClass === "all" || record.asset_class === state.selectedClass;
    return classOk;
  });
}

function populateControls() {
  const dates = tradingDates().sort().reverse();
  els.dateSelect.innerHTML = dates.map((date) => (
    `<option value="${escapeHtml(date)}">${escapeHtml(date)}</option>`
  )).join("");
  els.dateSelect.value = state.selectedDate;

  const availableClasses = new Set(allSeries().map((item) => item.asset_class).filter(Boolean));
  const classes = classOrder.filter((value) => availableClasses.has(value));
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
  const rankingRecords = records.filter((record) => record.source_sheet !== globalIndexSourceSheet);
  const gainers = rankingRecords
    .filter((item) => isNumber(item.daily_pct_change) && item.daily_pct_change > 0)
    .sort((a, b) => b.daily_pct_change - a.daily_pct_change)
    .slice(0, 5);
  const decliners = rankingRecords
    .filter((item) => isNumber(item.daily_pct_change) && item.daily_pct_change < 0)
    .sort((a, b) => a.daily_pct_change - b.daily_pct_change)
    .slice(0, 5);

  const renderList = (items, emptyText) => {
    if (!items.length) return `<div class="empty mover-empty">${escapeHtml(emptyText)}</div>`;
    return items.map((record, idx) => {
      const title = titleLine(record);
      const metricText = splitMetricDetailText(record);
      const metricHtml = metricText.note
        ? `<div class="metric-cell"><div class="metric-main">${escapeHtml(metricText.main)}</div><div class="metric-note">${escapeHtml(metricText.note)}</div></div>`
        : `<div class="metric-cell"><div class="metric-main">${escapeHtml(metricText.main)}</div></div>`;
      const rankBadge = idx === 0 ? '<span class="mover-rank">★</span>' : '';
      return `<div class="mover-item${idx === 0 ? " rank-leader" : ""}">
        <div>
          <div class="mover-title">${rankBadge}<strong>${escapeHtml(title)}</strong></div>
          ${metricHtml}
        </div>
        <div class="change ${severityClass(record)}">${severityMark(record)} ${escapeHtml(formatDailyChangeText(record))}</div>
      </div>`;
    }).join("");
  };

  els.moverList.innerHTML = `
    <div class="mover-column">
      <div class="mover-column-head">
        <strong>涨幅 TOP5</strong>
      </div>
      ${renderList(gainers, "暂无正向涨幅指标")}
    </div>
    <div class="mover-column">
      <div class="mover-column-head">
        <strong>跌幅 TOP5</strong>
      </div>
      ${renderList(decliners, "暂无负向跌幅指标")}
    </div>`;
}

function formatDailyChangeText(record) {
  if (!hasFlowChangeStatus(record)) {
    return record?.ticker === "USDCNY.EX"
      ? formatPctFixed(record.daily_pct_change, 2)
      : formatPct(record.daily_pct_change);
  }
  const statusText = String(record.flow_display_text || "").trim();
  if (isNumber(record.daily_pct_change)) {
    const pctText = record?.ticker === "USDCNY.EX"
      ? formatPctFixed(record.daily_pct_change, 2)
      : formatPct(record.daily_pct_change);
    return statusText ? `${statusText}（${pctText}）` : pctText;
  }
  return statusText || "--";
}

function renderTable(records) {
  const visible = records.filter((record) => record.source_sheet !== "权益-全球股指").slice(0, 120);
  const grouped = new Map();
  visible.forEach((record) => {
    const group = detailGroupLabel(record);
    if (!grouped.has(group)) grouped.set(group, []);
    grouped.get(group).push(record);
  });

  const renderRow = (record) => {
    const optionLot = isOptionLotMetric(record);
    const marginBalance = isMarginBalanceMetric(record);
    const retailFlow = isRetailFlowMetric(record);
    const valueText = optionLot
      ? formatOptionLotValue(record.value)
      : marginBalance
        ? formatMarginBalanceValue(record.value)
        : retailFlow
          ? formatRetailFlowValue(record.value)
          : formatValueFixed(record.value, record.unit, 2);
    const absChangeText = optionLot
      ? formatSignedValueFixed(Number.isFinite(record.daily_abs_change) ? record.daily_abs_change / 10000 : record.daily_abs_change, "万张", 2)
      : marginBalance
        ? formatMarginBalanceChange(record.daily_abs_change)
        : retailFlow
          ? formatRetailFlowChange(record.daily_abs_change)
          : formatSignedValueFixed(record.daily_abs_change, record.unit, 2);
    const pctText = formatDailyChangeText(record);
    const metricText = splitMetricDetailText(record);
    const metricCell = metricText.note
      ? `<div class="metric-cell"><div class="metric-main">${escapeHtml(metricText.main)}</div><div class="metric-note">${escapeHtml(metricText.note)}</div></div>`
      : `<div class="metric-cell"><div class="metric-main">${escapeHtml(metricText.main)}</div></div>`;
    return `<tr>
      <td>${escapeHtml(record.source_sheet)}</td>
      <td>${escapeHtml(labelAssetDetail(record))}</td>
      <td>${metricCell}</td>
      <td class="numeric">${renderNumericHtml(valueText)}</td>
      <td class="numeric change ${signedClass(record.daily_abs_change)}">${renderNumericHtml(absChangeText)}</td>
      <td class="numeric change ${severityClass(record)}">${renderNumericHtml(pctText)}</td>
    </tr>`;
  };

  const sections = [];
  detailGroupOrder.forEach((group) => {
    const rows = grouped.get(group) || [];
    if (!rows.length) return;
    sections.push(`<tr class="section-row"><td colspan="6">${escapeHtml(group)}</td></tr>`);
    sections.push(...rows.map(renderRow));
    grouped.delete(group);
  });

  for (const [group, rows] of grouped.entries()) {
    if (!rows.length) continue;
    sections.push(`<tr class="section-row"><td colspan="6">${escapeHtml(group)}</td></tr>`);
    sections.push(...rows.map(renderRow));
  }

  els.detailRows.innerHTML = sections.join("");
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

function drawVixChart() {
  const canvas = els.vixCanvas;
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(260, rect.width) * ratio;
  canvas.height = Math.max(160, rect.height) * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = canvas.width / ratio;
  const height = canvas.height / ratio;
  const pad = { left: 42, right: 14, top: 16, bottom: 30 };
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#071421";
  ctx.fillRect(0, 0, width, height);

  const points = vixPoints();
  if (!points.length) {
    ctx.fillStyle = "#93a6bd";
    ctx.font = "12px Segoe UI";
    ctx.fillText("暂无VIX数据", pad.left, height / 2);
    return;
  }

  const dates = points.map((point) => point.date);
  const values = points.map((point) => point.value);
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

  ctx.strokeStyle = "rgba(147, 166, 189, 0.16)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#93a6bd";
  ctx.font = "11px Segoe UI";
  for (let i = 0; i <= 3; i += 1) {
    const yy = pad.top + (i / 3) * plotH;
    const label = max - ((max - min) * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillText(formatNumber(label, 0), 8, yy + 4);
  }

  monthTicks(dates).forEach((tick, idx, ticks) => {
    const xx = x(tick.date);
    ctx.textAlign = idx === 0 ? "left" : idx === ticks.length - 1 ? "right" : "center";
    ctx.fillText(tick.label, xx, height - 10);
  });
  ctx.textAlign = "left";

  ctx.strokeStyle = "#f36d7a";
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  points.forEach((point, idx) => {
    const xx = x(point.date);
    const yy = y(point.value);
    if (idx === 0) ctx.moveTo(xx, yy);
    else ctx.lineTo(xx, yy);
  });
  ctx.stroke();
}

function drawLineChart(canvas, points, options) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(260, rect.width) * ratio;
  canvas.height = Math.max(160, rect.height) * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = canvas.width / ratio;
  const height = canvas.height / ratio;
  const pad = { left: 42, right: 14, top: 16, bottom: 30 };
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#071421";
  ctx.fillRect(0, 0, width, height);

  if (!points.length) {
    ctx.fillStyle = "#93a6bd";
    ctx.font = "12px Segoe UI";
    ctx.fillText(options.emptyText, pad.left, height / 2);
    return;
  }

  const dates = points.map((point) => point.date);
  const values = points.map((point) => point.value);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  min = Math.floor(min * 10) / 10;
  max = Math.ceil(max * 10) / 10;

  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (date) => {
    const idx = dates.indexOf(date);
    return pad.left + (idx / Math.max(1, dates.length - 1)) * plotW;
  };
  const y = (value) => pad.top + ((max - value) / (max - min)) * plotH;

  ctx.strokeStyle = "rgba(147, 166, 189, 0.16)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#93a6bd";
  ctx.font = "11px Segoe UI";
  for (let i = 0; i <= 3; i += 1) {
    const yy = pad.top + (i / 3) * plotH;
    const label = max - ((max - min) * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillText(formatNumber(label, 2), 8, yy + 4);
  }

  monthTicks(dates).forEach((tick, idx, ticks) => {
    const xx = x(tick.date);
    ctx.textAlign = idx === 0 ? "left" : idx === ticks.length - 1 ? "right" : "center";
    ctx.fillText(tick.label, xx, height - 10);
  });
  ctx.textAlign = "left";

  ctx.strokeStyle = options.color;
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  points.forEach((point, idx) => {
    const xx = x(point.date);
    const yy = y(point.value);
    if (idx === 0) ctx.moveTo(xx, yy);
    else ctx.lineTo(xx, yy);
  });
  ctx.stroke();
}

function drawTreasuryChart() {
  drawLineChart(els.treasuryCanvas, treasuryPoints(), {
    color: "#46c5bb",
    emptyText: "暂无美国10年期国债收益率数据",
  });
}

function render() {
  if (!state.payload) return;
  populateControls();
  const records = filteredRecords();
  renderGlobalIndexList();
  drawGlobalPerformanceChart();
  drawVixChart();
  drawTreasuryChart();
  renderMovers(records);
  renderTable(records);
}

async function exportLongImage() {
  if (!window.html2canvas) {
    window.alert("导出组件未加载，请刷新页面后重试。");
    return;
  }

  const docEl = document.documentElement;
  const body = document.body;
  const width = Math.max(docEl.scrollWidth, body.scrollWidth, docEl.clientWidth);
  const height = Math.max(docEl.scrollHeight, body.scrollHeight, docEl.clientHeight);

  const canvas = await window.html2canvas(body, {
    backgroundColor: "#06111f",
    scale: 1,
    useCORS: true,
    allowTaint: true,
    logging: false,
    width,
    height,
    windowWidth: docEl.clientWidth,
    windowHeight: docEl.clientHeight,
    scrollX: 0,
    scrollY: 0,
  });

  const link = document.createElement("a");
  link.download = `宏观市场核心指标看板-${state.selectedDate || "export"}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

async function init() {
  try {
    const response = await fetch("data/dashboard_data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    state.selectedDate = latestTradingDateOnOrBefore(todayDateString());
    populateControls();
    render();
  } catch (error) {
    els.moverList.innerHTML = `<div class="empty">数据加载失败：${escapeHtml(error.message)}</div>`;
    drawGlobalPerformanceChart();
    drawVixChart();
    drawTreasuryChart();
  }
}

els.dateSelect.addEventListener("change", (event) => {
  state.selectedDate = event.target.value;
  render();
});

els.exportLongImage.addEventListener("click", () => {
  exportLongImage().catch((error) => {
    window.alert(`导出失败：${error.message}`);
  });
});

window.addEventListener("resize", () => {
  drawGlobalPerformanceChart();
  drawVixChart();
  drawTreasuryChart();
});

init();
