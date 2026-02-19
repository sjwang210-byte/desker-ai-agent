import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

// ─────────────────────────────────────────
// 세션 생성
// ─────────────────────────────────────────

export const createSession = mutation({
  args: {
    filename: v.string(),
    sheetCount: v.number(),
    totalProducts: v.number(),
    sheets: v.array(v.object({
      sheetName: v.string(),
      productCount: v.number(),
    })),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("marketResearchSessions", {
      filename: args.filename,
      uploadedAt: Date.now(),
      sheetCount: args.sheetCount,
      totalProducts: args.totalProducts,
      sheets: args.sheets,
    });
  },
});

// ─────────────────────────────────────────
// 카테고리 생성
// ─────────────────────────────────────────

export const createCategory = mutation({
  args: {
    sessionId: v.id("marketResearchSessions"),
    name: v.string(),
    specFields: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    // 같은 세션에서 같은 이름의 카테고리가 있으면 반환
    const existing = await ctx.db
      .query("marketCategories")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
    const found = existing.find((c) => c.name === args.name);
    if (found) return found._id;

    return await ctx.db.insert("marketCategories", {
      sessionId: args.sessionId,
      name: args.name,
      specFields: args.specFields,
    });
  },
});

// ─────────────────────────────────────────
// 제품 일괄 삽입
// ─────────────────────────────────────────

export const insertProducts = mutation({
  args: {
    products: v.array(v.object({
      sessionId: v.id("marketResearchSessions"),
      categoryId: v.id("marketCategories"),
      name: v.string(),
      brand: v.string(),
      price: v.float64(),
      shippingFee: v.optional(v.string()),
      actualPrice: v.optional(v.float64()),
      seller: v.optional(v.string()),
      material: v.optional(v.string()),
      origin: v.optional(v.string()),
      url: v.optional(v.string()),
      specs: v.any(),
      isOurProduct: v.boolean(),
    })),
  },
  handler: async (ctx, args) => {
    for (const product of args.products) {
      await ctx.db.insert("marketProducts", product);
    }
    return args.products.length;
  },
});

// ─────────────────────────────────────────
// 세션 목록 조회
// ─────────────────────────────────────────

export const listSessions = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("marketResearchSessions")
      .withIndex("by_uploadedAt")
      .order("desc")
      .take(50);
  },
});

// ─────────────────────────────────────────
// 세션의 카테고리 목록
// ─────────────────────────────────────────

export const getCategories = query({
  args: { sessionId: v.id("marketResearchSessions") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("marketCategories")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
  },
});

// ─────────────────────────────────────────
// 카테고리별 제품 조회
// ─────────────────────────────────────────

export const getProductsByCategory = query({
  args: { categoryId: v.id("marketCategories") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("marketProducts")
      .withIndex("by_category", (q) => q.eq("categoryId", args.categoryId))
      .collect();
  },
});

// ─────────────────────────────────────────
// 세션의 전체 제품 조회
// ─────────────────────────────────────────

export const getAllProducts = query({
  args: { sessionId: v.id("marketResearchSessions") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("marketProducts")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
  },
});

// ─────────────────────────────────────────
// 세션 삭제 (관련 데이터 모두 삭제)
// ─────────────────────────────────────────

export const deleteSession = mutation({
  args: { sessionId: v.id("marketResearchSessions") },
  handler: async (ctx, args) => {
    // 제품 삭제
    const products = await ctx.db
      .query("marketProducts")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
    for (const p of products) {
      await ctx.db.delete(p._id);
    }

    // 카테고리 삭제
    const categories = await ctx.db
      .query("marketCategories")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
    for (const c of categories) {
      await ctx.db.delete(c._id);
    }

    // 세션 삭제
    await ctx.db.delete(args.sessionId);
    return products.length;
  },
});
