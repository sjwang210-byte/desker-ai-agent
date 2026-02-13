import { v } from "convex/values";
import { query } from "./_generated/server";
import { Doc, Id } from "./_generated/dataModel";

// ─────────────────────────────────────────
// 내부 헬퍼 함수
// ─────────────────────────────────────────

type PRecord = Doc<"profileRecords">;
type ProdInfo = { name: string; catId: string };
type CatInfo = { L1: string; L2: string; L3: string };

/** 여러 세션에서 프로파일 레코드 수집 */
async function collectRecords(
  ctx: any,
  sessionIds: Id<"uploadSessions">[],
  dimension: string,
  excludeUnknown: boolean,
): Promise<PRecord[]> {
  let all: PRecord[] = [];
  for (const sid of sessionIds) {
    const recs = await ctx.db
      .query("profileRecords")
      .withIndex("by_session_dimension", (q: any) =>
        q.eq("sessionId", sid).eq("dimension", dimension)
      )
      .collect();
    all = all.concat(recs);
  }
  if (excludeUnknown) {
    all = all.filter((r: PRecord) => r.attributeValue !== "(알수없음)");
  }
  return all;
}

/** 상품/카테고리 캐시 구축 */
async function buildCaches(ctx: any, records: PRecord[]) {
  const prodCache: Record<string, ProdInfo> = {};
  const catCache: Record<string, CatInfo> = {};

  for (const rec of records) {
    const pid = rec.productId as unknown as string;
    if (!prodCache[pid]) {
      const product = await ctx.db.get(rec.productId);
      if (!product) continue;
      prodCache[pid] = {
        name: product.productName,
        catId: product.categoryId as unknown as string,
      };
    }
    const catId = prodCache[pid].catId;
    if (!catCache[catId]) {
      const cat = await ctx.db.get(prodCache[pid].catId as any);
      if (!cat) continue;
      catCache[catId] = {
        L1: cat.categoryL1,
        L2: cat.categoryL2,
        L3: cat.categoryL3,
      };
    }
  }
  return { prodCache, catCache };
}

/** 그룹 키 결정 */
function groupKey(
  rec: PRecord,
  level: string,
  prodCache: Record<string, ProdInfo>,
  catCache: Record<string, CatInfo>,
): string {
  const pid = rec.productId as unknown as string;
  const p = prodCache[pid];
  if (!p) return "unknown";
  const cat = catCache[p.catId];
  if (!cat) return "unknown";
  switch (level) {
    case "L1": return cat.L1;
    case "L2": return cat.L2;
    case "L3": return cat.L3;
    case "product": return p.name;
    default: return cat.L2;
  }
}

/** 지표값 추출 */
function metricVal(rec: PRecord, metric: string): number {
  switch (metric) {
    case "paymentAmount": return rec.paymentAmount;
    case "paymentCount": return rec.paymentCount;
    case "paymentQuantity": return rec.paymentQuantity;
    default: return rec.paymentAmount;
  }
}

/** 비중 계산 공통 로직 */
function calcDistribution(
  records: PRecord[],
  level: string,
  metric: string,
  prodCache: Record<string, ProdInfo>,
  catCache: Record<string, CatInfo>,
) {
  const groups: Record<string, Record<string, number>> = {};
  for (const rec of records) {
    const key = groupKey(rec, level, prodCache, catCache);
    if (key === "unknown") continue;
    if (!groups[key]) groups[key] = {};
    groups[key][rec.attributeValue] =
      (groups[key][rec.attributeValue] || 0) + metricVal(rec, metric);
  }

  return Object.entries(groups)
    .map(([category, attrs]) => {
      const total = Object.values(attrs).reduce((s, v) => s + v, 0);
      const distribution = Object.entries(attrs)
        .map(([attributeValue, absoluteValue]) => ({
          attributeValue,
          percentage: total > 0 ? Math.round((absoluteValue / total) * 1000) / 10 : 0,
          absoluteValue,
        }))
        .sort((a, b) => b.percentage - a.percentage);
      return { category, total, distribution };
    })
    .sort((a, b) => b.total - a.total);
}

// ─────────────────────────────────────────
// 세션/기간 관련
// ─────────────────────────────────────────

export const listSessions = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("uploadSessions")
      .withIndex("by_uploadedAt")
      .order("desc")
      .take(50);
  },
});

export const getSession = query({
  args: { sessionId: v.id("uploadSessions") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.sessionId);
  },
});

/** 사용 가능한 기간(월) 목록 */
export const getAvailableMonths = query({
  args: {},
  handler: async (ctx) => {
    const sessions = await ctx.db
      .query("uploadSessions")
      .withIndex("by_uploadedAt")
      .order("desc")
      .collect();

    return sessions.map((s) => ({
      sessionId: s._id,
      periodStart: s.periodStart,
      periodEnd: s.periodEnd,
      fileCount: s.files ? s.files.length : 0,
      dimensions: s.files
        ? s.files.map((f: { dimension: string }) => f.dimension)
        : [],
      status: s.status,
      uploadedAt: s.uploadedAt,
    }));
  },
});

// ─────────────────────────────────────────
// 카테고리
// ─────────────────────────────────────────

export const getCategories = query({
  args: { level: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("productCategories").collect();
    if (!args.level || args.level === "L1") {
      return [...new Set(all.map((c) => c.categoryL1))].sort();
    }
    if (args.level === "L2") {
      return [...new Set(all.map((c) => c.categoryL2))].sort();
    }
    if (args.level === "L3") {
      return [...new Set(all.map((c) => c.categoryL3))].sort();
    }
    return all;
  },
});

export const getCategoryHierarchy = query({
  args: {},
  handler: async (ctx) => {
    const all = await ctx.db.query("productCategories").collect();
    const tree: Record<string, Record<string, string[]>> = {};
    for (const cat of all) {
      if (!tree[cat.categoryL1]) tree[cat.categoryL1] = {};
      if (!tree[cat.categoryL1][cat.categoryL2])
        tree[cat.categoryL1][cat.categoryL2] = [];
      if (!tree[cat.categoryL1][cat.categoryL2].includes(cat.categoryL3))
        tree[cat.categoryL1][cat.categoryL2].push(cat.categoryL3);
    }
    return tree;
  },
});

// ─────────────────────────────────────────
// 비중 분석 (다중 세션 = 누적 지원)
// ─────────────────────────────────────────

export const getPercentageDistribution = query({
  args: {
    sessionIds: v.array(v.id("uploadSessions")),
    dimension: v.string(),
    aggregationLevel: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    const records = await collectRecords(
      ctx, args.sessionIds, args.dimension, args.excludeUnknown,
    );
    const { prodCache, catCache } = await buildCaches(ctx, records);
    return calcDistribution(
      records, args.aggregationLevel, args.metric, prodCache, catCache,
    );
  },
});

// ─────────────────────────────────────────
// 통합 분석 (3차원 동시, 다중 세션)
// ─────────────────────────────────────────

export const getIntegratedView = query({
  args: {
    sessionIds: v.array(v.id("uploadSessions")),
    aggregationLevel: v.string(),
    category: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    const dimensions = ["자녀나이", "결혼상태", "가구당인원"];
    const results = [];

    for (const dimension of dimensions) {
      const records = await collectRecords(
        ctx, args.sessionIds, dimension, args.excludeUnknown,
      );
      const { prodCache, catCache } = await buildCaches(ctx, records);

      // 해당 카테고리에 속하는 레코드 필터
      const filtered = records.filter((rec) => {
        const pid = rec.productId as unknown as string;
        const p = prodCache[pid];
        if (!p) return false;
        const cat = catCache[p.catId];
        if (!cat) return false;
        switch (args.aggregationLevel) {
          case "L1": return cat.L1 === args.category;
          case "L2": return cat.L2 === args.category;
          case "L3": return cat.L3 === args.category;
          case "product": return p.name === args.category;
        }
        return false;
      });

      const sums: Record<string, number> = {};
      for (const rec of filtered) {
        sums[rec.attributeValue] =
          (sums[rec.attributeValue] || 0) + metricVal(rec, args.metric);
      }

      const total = Object.values(sums).reduce((s, v) => s + v, 0);
      const distribution = Object.entries(sums)
        .map(([attributeValue, absoluteValue]) => ({
          attributeValue,
          percentage:
            total > 0
              ? Math.round((absoluteValue / total) * 1000) / 10
              : 0,
          absoluteValue,
        }))
        .sort((a, b) => b.percentage - a.percentage);

      results.push({ dimension, total, distribution });
    }

    return results;
  },
});

// ─────────────────────────────────────────
// 드릴다운 (다중 세션)
// ─────────────────────────────────────────

export const getDrilldown = query({
  args: {
    sessionIds: v.array(v.id("uploadSessions")),
    dimension: v.string(),
    parentLevel: v.string(),
    parentValue: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    const childLevel =
      args.parentLevel === "L1"
        ? "L2"
        : args.parentLevel === "L2"
          ? "L3"
          : "product";

    const records = await collectRecords(
      ctx, args.sessionIds, args.dimension, args.excludeUnknown,
    );
    const { prodCache, catCache } = await buildCaches(ctx, records);

    // 부모 카테고리 필터 + 자식 레벨 그룹핑
    const groups: Record<string, Record<string, number>> = {};
    for (const rec of records) {
      const pid = rec.productId as unknown as string;
      const p = prodCache[pid];
      if (!p) continue;
      const cat = catCache[p.catId];
      if (!cat) continue;

      let parentMatch = false;
      if (args.parentLevel === "L1") parentMatch = cat.L1 === args.parentValue;
      else if (args.parentLevel === "L2")
        parentMatch = cat.L2 === args.parentValue;
      else if (args.parentLevel === "L3")
        parentMatch = cat.L3 === args.parentValue;
      if (!parentMatch) continue;

      let childKey = "";
      if (childLevel === "L2") childKey = cat.L2;
      else if (childLevel === "L3") childKey = cat.L3;
      else childKey = p.name;

      if (!groups[childKey]) groups[childKey] = {};
      groups[childKey][rec.attributeValue] =
        (groups[childKey][rec.attributeValue] || 0) +
        metricVal(rec, args.metric);
    }

    return Object.entries(groups)
      .map(([category, attrs]) => {
        const total = Object.values(attrs).reduce((s, v) => s + v, 0);
        const distribution = Object.entries(attrs)
          .map(([attributeValue, absoluteValue]) => ({
            attributeValue,
            percentage:
              total > 0
                ? Math.round((absoluteValue / total) * 1000) / 10
                : 0,
            absoluteValue,
          }))
          .sort((a, b) => b.percentage - a.percentage);
        return { category, total, distribution };
      })
      .sort((a, b) => b.total - a.total);
  },
});

// ─────────────────────────────────────────
// 리뷰 세션 목록
// ─────────────────────────────────────────

export const listReviewSessions = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("reviewSessions")
      .withIndex("by_uploadedAt")
      .order("desc")
      .take(50);
  },
});

// ─────────────────────────────────────────
// 리뷰 데이터 로드 (세션 ID 배열)
// ─────────────────────────────────────────

export const getReviews = query({
  args: {
    sessionIds: v.array(v.id("reviewSessions")),
  },
  handler: async (ctx, args) => {
    let all: any[] = [];
    for (const sid of args.sessionIds) {
      const reviews = await ctx.db
        .query("reviews")
        .withIndex("by_session", (q: any) => q.eq("sessionId", sid))
        .collect();
      all = all.concat(reviews);
    }
    return all;
  },
});

// ─────────────────────────────────────────
// 리뷰 카테고리 목록 (세션 기반)
// ─────────────────────────────────────────

export const getReviewCategories = query({
  args: {
    sessionIds: v.array(v.id("reviewSessions")),
  },
  handler: async (ctx, args) => {
    const catCounts: Record<string, number> = {};
    for (const sid of args.sessionIds) {
      const reviews = await ctx.db
        .query("reviews")
        .withIndex("by_session", (q: any) => q.eq("sessionId", sid))
        .collect();
      for (const r of reviews) {
        catCounts[r.category] = (catCounts[r.category] || 0) + 1;
      }
    }
    return Object.entries(catCounts)
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count);
  },
});
