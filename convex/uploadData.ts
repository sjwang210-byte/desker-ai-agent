import { v } from "convex/values";
import { mutation } from "./_generated/server";

// ─────────────────────────────────────────
// 업로드 세션 생성/업데이트
// ─────────────────────────────────────────

export const createSession = mutation({
  args: {
    periodStart: v.string(),
    periodEnd: v.string(),
  },
  handler: async (ctx, args) => {
    // 같은 기간의 기존 세션 확인
    const existing = await ctx.db
      .query("uploadSessions")
      .withIndex("by_period", (q) =>
        q.eq("periodStart", args.periodStart).eq("periodEnd", args.periodEnd)
      )
      .first();

    if (existing) return existing._id;

    return await ctx.db.insert("uploadSessions", {
      periodStart: args.periodStart,
      periodEnd: args.periodEnd,
      uploadedAt: Date.now(),
      files: [],
      status: "partial",
    });
  },
});

// ─────────────────────────────────────────
// 카테고리 + 상품 upsert (중복 방지)
// ─────────────────────────────────────────

export const upsertCategory = mutation({
  args: {
    categoryL1: v.string(),
    categoryL2: v.string(),
    categoryL3: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("productCategories")
      .withIndex("by_hierarchy", (q) =>
        q
          .eq("categoryL1", args.categoryL1)
          .eq("categoryL2", args.categoryL2)
          .eq("categoryL3", args.categoryL3)
      )
      .first();

    if (existing) return existing._id;

    return await ctx.db.insert("productCategories", args);
  },
});

export const upsertProduct = mutation({
  args: {
    productId: v.float64(),
    productName: v.string(),
    categoryId: v.id("productCategories"),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("products")
      .withIndex("by_productId", (q) => q.eq("productId", args.productId))
      .first();

    if (existing) return existing._id;

    return await ctx.db.insert("products", args);
  },
});

// ─────────────────────────────────────────
// 프로파일 레코드 일괄 삽입 (배치)
// ─────────────────────────────────────────

export const insertProfileRecords = mutation({
  args: {
    records: v.array(
      v.object({
        sessionId: v.id("uploadSessions"),
        productId: v.id("products"),
        dimension: v.string(),
        attributeValue: v.string(),
        paymentAmount: v.float64(),
        paymentCount: v.number(),
        paymentQuantity: v.number(),
        refundAmount: v.float64(),
        refundCount: v.number(),
        refundQuantity: v.number(),
      })
    ),
  },
  handler: async (ctx, args) => {
    const ids = [];
    for (const record of args.records) {
      const id = await ctx.db.insert("profileRecords", record);
      ids.push(id);
    }
    return ids.length;
  },
});

// ─────────────────────────────────────────
// 세션 파일 정보 업데이트
// ─────────────────────────────────────────

export const updateSessionFile = mutation({
  args: {
    sessionId: v.id("uploadSessions"),
    dimension: v.string(),
    filename: v.string(),
    rowCount: v.number(),
  },
  handler: async (ctx, args) => {
    const session = await ctx.db.get(args.sessionId);
    if (!session) throw new Error("Session not found");

    const files = session.files.filter(
      (f: { dimension: string }) => f.dimension !== args.dimension
    );
    files.push({
      dimension: args.dimension,
      filename: args.filename,
      rowCount: args.rowCount,
    });

    const status = files.length >= 3 ? "complete" : "partial";

    await ctx.db.patch(args.sessionId, { files, status });
  },
});

// ─────────────────────────────────────────
// 세션의 특정 차원 데이터 삭제 (재업로드용)
// ─────────────────────────────────────────

export const deleteSessionDimension = mutation({
  args: {
    sessionId: v.id("uploadSessions"),
    dimension: v.string(),
  },
  handler: async (ctx, args) => {
    const records = await ctx.db
      .query("profileRecords")
      .withIndex("by_session_dimension", (q) =>
        q.eq("sessionId", args.sessionId).eq("dimension", args.dimension)
      )
      .collect();

    for (const record of records) {
      await ctx.db.delete(record._id);
    }

    return records.length;
  },
});

// ─────────────────────────────────────────
// 리뷰 세션 생성
// ─────────────────────────────────────────

export const createReviewSession = mutation({
  args: {
    filename: v.string(),
    rowCount: v.number(),
    productCount: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("reviewSessions", {
      filename: args.filename,
      uploadedAt: Date.now(),
      rowCount: args.rowCount,
      productCount: args.productCount,
    });
  },
});

// ─────────────────────────────────────────
// 리뷰 레코드 일괄 삽입 (배치)
// ─────────────────────────────────────────

export const insertReviews = mutation({
  args: {
    reviews: v.array(
      v.object({
        sessionId: v.id("reviewSessions"),
        productId: v.string(),
        productName: v.string(),
        category: v.string(),
        rating: v.number(),
        content: v.string(),
        date: v.string(),
        reviewType: v.string(),
        isMonth: v.boolean(),
        hasPhoto: v.boolean(),
        isBest: v.boolean(),
        helpful: v.number(),
        author: v.string(),
        photos: v.array(v.string()),
      })
    ),
  },
  handler: async (ctx, args) => {
    for (const review of args.reviews) {
      await ctx.db.insert("reviews", review);
    }
    return args.reviews.length;
  },
});

// ─────────────────────────────────────────
// 리뷰 세션 삭제
// ─────────────────────────────────────────

export const deleteReviewSession = mutation({
  args: { sessionId: v.id("reviewSessions") },
  handler: async (ctx, args) => {
    const reviews = await ctx.db
      .query("reviews")
      .withIndex("by_session", (q) => q.eq("sessionId", args.sessionId))
      .collect();
    for (const r of reviews) {
      await ctx.db.delete(r._id);
    }
    await ctx.db.delete(args.sessionId);
    return reviews.length;
  },
});
