import { v } from "convex/values";
import { query } from "./_generated/server";

// ─────────────────────────────────────────
// 세션 목록 조회
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

// ─────────────────────────────────────────
// 카테고리 목록 조회
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

    // 대분류 → 중분류 → 소분류 트리 구조
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
// 비중 분석 쿼리 (핵심)
// ─────────────────────────────────────────

export const getPercentageDistribution = query({
  args: {
    sessionId: v.id("uploadSessions"),
    dimension: v.string(),
    aggregationLevel: v.string(), // "L1" | "L2" | "L3" | "product"
    metric: v.string(),           // "paymentAmount" | "paymentCount" | "paymentQuantity"
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    // 해당 세션 + 차원의 모든 레코드
    let records = await ctx.db
      .query("profileRecords")
      .withIndex("by_session_dimension", (q) =>
        q.eq("sessionId", args.sessionId).eq("dimension", args.dimension)
      )
      .collect();

    if (args.excludeUnknown) {
      records = records.filter((r) => r.attributeValue !== "(알수없음)");
    }

    // 상품 + 카테고리 조인
    const productCache: Record<string, { name: string; catId: string }> = {};
    const categoryCache: Record<
      string,
      { L1: string; L2: string; L3: string }
    > = {};

    for (const rec of records) {
      const pid = rec.productId as string;
      if (!productCache[pid]) {
        const product = await ctx.db.get(rec.productId);
        if (!product) continue;
        productCache[pid] = {
          name: product.productName,
          catId: product.categoryId as string,
        };
      }
      const catId = productCache[pid].catId;
      if (!categoryCache[catId]) {
        const cat = await ctx.db.get(productCache[pid].catId as any);
        if (!cat) continue;
        categoryCache[catId] = {
          L1: cat.categoryL1,
          L2: cat.categoryL2,
          L3: cat.categoryL3,
        };
      }
    }

    // 집계 레벨에 따른 그룹핑
    const getGroupKey = (rec: (typeof records)[0]): string => {
      const pid = rec.productId as string;
      const p = productCache[pid];
      if (!p) return "unknown";
      const cat = categoryCache[p.catId];
      if (!cat) return "unknown";

      switch (args.aggregationLevel) {
        case "L1":
          return cat.L1;
        case "L2":
          return cat.L2;
        case "L3":
          return cat.L3;
        case "product":
          return p.name;
        default:
          return cat.L2;
      }
    };

    const getMetricValue = (rec: (typeof records)[0]): number => {
      switch (args.metric) {
        case "paymentAmount":
          return rec.paymentAmount;
        case "paymentCount":
          return rec.paymentCount;
        case "paymentQuantity":
          return rec.paymentQuantity;
        default:
          return rec.paymentAmount;
      }
    };

    // 그룹별 속성값 합산
    const groups: Record<string, Record<string, number>> = {};
    for (const rec of records) {
      const key = getGroupKey(rec);
      if (key === "unknown") continue;
      if (!groups[key]) groups[key] = {};
      groups[key][rec.attributeValue] =
        (groups[key][rec.attributeValue] || 0) + getMetricValue(rec);
    }

    // 비율 계산 + 정렬
    const result = Object.entries(groups)
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

    return result;
  },
});

// ─────────────────────────────────────────
// 통합 분석 (3차원 동시)
// ─────────────────────────────────────────

export const getIntegratedView = query({
  args: {
    sessionId: v.id("uploadSessions"),
    aggregationLevel: v.string(),
    category: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    const dimensions = ["자녀나이", "결혼상태", "가구당인원"];
    const results = [];

    for (const dimension of dimensions) {
      let records = await ctx.db
        .query("profileRecords")
        .withIndex("by_session_dimension", (q) =>
          q.eq("sessionId", args.sessionId).eq("dimension", dimension)
        )
        .collect();

      if (args.excludeUnknown) {
        records = records.filter((r) => r.attributeValue !== "(알수없음)");
      }

      // 해당 카테고리에 속하는 레코드 필터
      const filtered = [];
      for (const rec of records) {
        const product = await ctx.db.get(rec.productId);
        if (!product) continue;
        const cat = await ctx.db.get(product.categoryId);
        if (!cat) continue;

        let match = false;
        switch (args.aggregationLevel) {
          case "L1":
            match = cat.categoryL1 === args.category;
            break;
          case "L2":
            match = cat.categoryL2 === args.category;
            break;
          case "L3":
            match = cat.categoryL3 === args.category;
            break;
          case "product":
            match = product.productName === args.category;
            break;
        }
        if (match) filtered.push(rec);
      }

      // 속성값별 합산
      const sums: Record<string, number> = {};
      for (const rec of filtered) {
        const val =
          args.metric === "paymentCount"
            ? rec.paymentCount
            : args.metric === "paymentQuantity"
              ? rec.paymentQuantity
              : rec.paymentAmount;
        sums[rec.attributeValue] = (sums[rec.attributeValue] || 0) + val;
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
// 드릴다운 (상위 카테고리 → 하위)
// ─────────────────────────────────────────

export const getDrilldown = query({
  args: {
    sessionId: v.id("uploadSessions"),
    dimension: v.string(),
    parentLevel: v.string(),    // "L1" | "L2"
    parentValue: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
  },
  handler: async (ctx, args) => {
    const childLevel =
      args.parentLevel === "L1" ? "L2" : args.parentLevel === "L2" ? "L3" : "product";

    let records = await ctx.db
      .query("profileRecords")
      .withIndex("by_session_dimension", (q) =>
        q.eq("sessionId", args.sessionId).eq("dimension", args.dimension)
      )
      .collect();

    if (args.excludeUnknown) {
      records = records.filter((r) => r.attributeValue !== "(알수없음)");
    }

    // 부모 카테고리에 속하는 레코드 필터 + 자식 레벨로 그룹핑
    const groups: Record<string, Record<string, number>> = {};

    for (const rec of records) {
      const product = await ctx.db.get(rec.productId);
      if (!product) continue;
      const cat = await ctx.db.get(product.categoryId);
      if (!cat) continue;

      // 부모 매칭
      let parentMatch = false;
      if (args.parentLevel === "L1") parentMatch = cat.categoryL1 === args.parentValue;
      else if (args.parentLevel === "L2") parentMatch = cat.categoryL2 === args.parentValue;
      else if (args.parentLevel === "L3") parentMatch = cat.categoryL3 === args.parentValue;
      if (!parentMatch) continue;

      // 자식 키
      let childKey = "";
      if (childLevel === "L2") childKey = cat.categoryL2;
      else if (childLevel === "L3") childKey = cat.categoryL3;
      else childKey = product.productName;

      const val =
        args.metric === "paymentCount"
          ? rec.paymentCount
          : args.metric === "paymentQuantity"
            ? rec.paymentQuantity
            : rec.paymentAmount;

      if (!groups[childKey]) groups[childKey] = {};
      groups[childKey][rec.attributeValue] =
        (groups[childKey][rec.attributeValue] || 0) + val;
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
  },
});
