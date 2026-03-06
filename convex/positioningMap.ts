import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

// ─────────────────────────────────────────
// 세션 목록 조회 (메타데이터만, sessionData 제외)
// ─────────────────────────────────────────
export const listSessions = query({
  args: {},
  handler: async (ctx) => {
    const sessions = await ctx.db
      .query("positioningMapSessions")
      .withIndex("by_savedAt")
      .order("desc")
      .take(20);
    return sessions.map((s) => ({
      _id: s._id,
      label: s.label,
      savedAt: s.savedAt,
      productCount: s.productCount,
      specCount: s.specCount,
      priceRange: s.priceRange,
    }));
  },
});

// ─────────────────────────────────────────
// 세션 상세 조회 (전체 데이터 포함)
// ─────────────────────────────────────────
export const getSession = query({
  args: { id: v.id("positioningMapSessions") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.id);
  },
});

// ─────────────────────────────────────────
// 세션 저장 (최대 20개 유지)
// ─────────────────────────────────────────
export const saveSession = mutation({
  args: {
    label: v.string(),
    savedAt: v.float64(),
    productCount: v.float64(),
    specCount: v.float64(),
    priceRange: v.string(),
    sessionData: v.any(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("positioningMapSessions", {
      label: args.label,
      savedAt: args.savedAt,
      productCount: args.productCount,
      specCount: args.specCount,
      priceRange: args.priceRange,
      sessionData: args.sessionData,
    });

    // 20개 초과 시 오래된 것 삭제
    const all = await ctx.db
      .query("positioningMapSessions")
      .withIndex("by_savedAt")
      .order("asc")
      .collect();
    if (all.length > 20) {
      const toDelete = all.slice(0, all.length - 20);
      for (const s of toDelete) {
        await ctx.db.delete(s._id);
      }
    }

    return id;
  },
});

// ─────────────────────────────────────────
// 세션 삭제
// ─────────────────────────────────────────
export const deleteSession = mutation({
  args: { id: v.id("positioningMapSessions") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
  },
});
