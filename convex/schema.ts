import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // ─────────────────────────────────────────
  // 1. 업로드 세션: 엑셀 파일 3종을 묶는 단위
  // ─────────────────────────────────────────
  uploadSessions: defineTable({
    periodStart: v.string(),     // "2025-07-01"
    periodEnd: v.string(),       // "2025-12-31"
    uploadedAt: v.number(),      // Date.now() timestamp
    files: v.array(v.object({
      dimension: v.string(),     // "자녀나이" | "결혼상태" | "가구당인원"
      filename: v.string(),
      rowCount: v.number(),
    })),
    status: v.string(),          // "partial" | "complete"
  })
    .index("by_period", ["periodStart", "periodEnd"])
    .index("by_uploadedAt", ["uploadedAt"]),

  // ─────────────────────────────────────────
  // 2. 상품 카테고리 계층 (3단계: 대/중/소)
  //    실제 컬럼: 상품카테고리(대), (중), (소)
  //    세분류는 대부분 "-"이므로 제외
  // ─────────────────────────────────────────
  productCategories: defineTable({
    categoryL1: v.string(),      // 상품카테고리(대): 3종 — 가구/인테리어, 디지털/가전, 생활/건강
    categoryL2: v.string(),      // 상품카테고리(중): 11종 — 아동/주니어가구, 서재/사무용가구 등
    categoryL3: v.string(),      // 상품카테고리(소): 22종 — 책상, 책장, 의자 등
  })
    .index("by_hierarchy", ["categoryL1", "categoryL2", "categoryL3"])
    .index("by_L1", ["categoryL1"])
    .index("by_L1_L2", ["categoryL1", "categoryL2"]),

  // ─────────────────────────────────────────
  // 3. 상품 마스터
  // ─────────────────────────────────────────
  products: defineTable({
    productId: v.float64(),      // 상품ID: 9423118946 (10자리 — JS safe integer 범위)
    productName: v.string(),     // 상품명
    categoryId: v.id("productCategories"),
  })
    .index("by_productId", ["productId"])
    .index("by_category", ["categoryId"]),

  // ─────────────────────────────────────────
  // 4. 프로파일 레코드 (핵심 — 엑셀 각 행)
  // ─────────────────────────────────────────
  profileRecords: defineTable({
    sessionId: v.id("uploadSessions"),
    productId: v.id("products"),

    dimension: v.string(),       // "자녀나이" | "결혼상태" | "가구당인원"
    attributeValue: v.string(),  // "초등학생", "기혼", "2인이상" 등

    // 결제 지표
    paymentAmount: v.float64(),  // 결제금액 (int64 → float64 for JS)
    paymentCount: v.number(),    // 결제수
    paymentQuantity: v.number(), // 결제상품수량

    // 환불 지표
    refundAmount: v.float64(),   // 환불금액 (과학적 표기법 3.847587e+08)
    refundCount: v.number(),     // 환불건수
    refundQuantity: v.number(),  // 환불수량
  })
    .index("by_session", ["sessionId"])
    .index("by_session_dimension", ["sessionId", "dimension"])
    .index("by_product", ["productId"])
    .index("by_dimension_attribute", ["dimension", "attributeValue"]),

  // ─────────────────────────────────────────
  // 5. 분석 결과 저장 (캐싱/공유용)
  // ─────────────────────────────────────────
  analysisResults: defineTable({
    sessionId: v.id("uploadSessions"),
    dimension: v.string(),       // "자녀나이" | "결혼상태" | "가구당인원"
    aggregationLevel: v.string(),// "상품카테고리(대)" | "(중)" | "(소)" | "상품"
    metric: v.string(),          // "결제금액" | "결제수" | "결제상품수량"
    excludeUnknown: v.boolean(),
    resultData: v.array(v.object({
      category: v.string(),
      total: v.float64(),
      distribution: v.array(v.object({
        attributeValue: v.string(),
        percentage: v.float64(),   // 0-100
        absoluteValue: v.float64(),
      })),
    })),
    createdAt: v.number(),
    createdBy: v.optional(v.string()),
  })
    .index("by_session", ["sessionId"])
    .index("by_params", ["sessionId", "dimension", "aggregationLevel", "metric"]),

  // ─────────────────────────────────────────
  // 6. 통합 분석 결과 (3차원 동시 분석)
  // ─────────────────────────────────────────
  integratedAnalysis: defineTable({
    sessionId: v.id("uploadSessions"),
    aggregationLevel: v.string(),
    category: v.string(),
    metric: v.string(),
    excludeUnknown: v.boolean(),
    dimensions: v.array(v.object({
      dimension: v.string(),
      total: v.float64(),
      distribution: v.array(v.object({
        attributeValue: v.string(),
        percentage: v.float64(),
        absoluteValue: v.float64(),
      })),
    })),
    createdAt: v.number(),
  })
    .index("by_session", ["sessionId"])
    .index("by_category", ["sessionId", "aggregationLevel", "category"]),

  // ─────────────────────────────────────────
  // 7. 리뷰 업로드 세션
  // ─────────────────────────────────────────
  reviewSessions: defineTable({
    filename: v.string(),
    uploadedAt: v.number(),
    rowCount: v.number(),
    productCount: v.number(),
  })
    .index("by_uploadedAt", ["uploadedAt"]),

  // ─────────────────────────────────────────
  // 8. 리뷰 레코드
  // ─────────────────────────────────────────
  reviews: defineTable({
    sessionId: v.id("reviewSessions"),
    productId: v.string(),        // 상품번호 (문자열)
    productName: v.string(),
    category: v.string(),         // 카테고리 (책상/테이블/책장 등)
    rating: v.number(),
    content: v.string(),
    date: v.string(),             // "2025-01-15"
    reviewType: v.string(),       // "일반" | "한달사용"
    isMonth: v.boolean(),
    hasPhoto: v.boolean(),
    isBest: v.boolean(),
    helpful: v.number(),
    author: v.string(),
    photos: v.array(v.string()),  // 이미지 URL 배열
  })
    .index("by_session", ["sessionId"])
    .index("by_product", ["productId"])
    .index("by_category", ["category"])
    .index("by_date", ["date"]),

  // ─────────────────────────────────────────
  // 9. 시장조사 업로드 세션
  // ─────────────────────────────────────────
  marketResearchSessions: defineTable({
    filename: v.string(),
    uploadedAt: v.number(),
    sheetCount: v.number(),        // 시트 수
    totalProducts: v.number(),     // 총 제품 수
    sheets: v.array(v.object({
      sheetName: v.string(),
      productCount: v.number(),
    })),
  })
    .index("by_uploadedAt", ["uploadedAt"]),

  // ─────────────────────────────────────────
  // 10. 시장조사 카테고리 (시트 = 품목 카테고리)
  //     실내 체어, 실외 체어, 바스툴 등
  // ─────────────────────────────────────────
  marketCategories: defineTable({
    sessionId: v.id("marketResearchSessions"),
    name: v.string(),              // 시트명 = 카테고리명 (실내 체어, 실외 체어, 바스툴)
    specFields: v.array(v.string()), // 해당 카테고리의 스펙 필드명 목록
  })
    .index("by_session", ["sessionId"])
    .index("by_name", ["name"]),

  // ─────────────────────────────────────────
  // 11. 시장조사 제품 (각 경쟁 제품)
  //     엑셀 전치형 데이터를 정규화하여 저장
  // ─────────────────────────────────────────
  marketProducts: defineTable({
    sessionId: v.id("marketResearchSessions"),
    categoryId: v.id("marketCategories"),
    name: v.string(),              // 제품명
    brand: v.string(),             // 브랜드
    price: v.float64(),            // 가격 (숫자)
    shippingFee: v.optional(v.string()),  // 배송비 ("무료" | "5000" 등)
    actualPrice: v.optional(v.float64()), // 실판매가 (가격+배송비)
    seller: v.optional(v.string()),       // 판매처
    material: v.optional(v.string()),     // 소재
    origin: v.optional(v.string()),       // 원산지
    url: v.optional(v.string()),          // URL
    specs: v.any(),                // 기타 스펙 (JSON — 유연한 key-value)
    isOurProduct: v.boolean(),     // 우리 제품 여부
  })
    .index("by_session", ["sessionId"])
    .index("by_category", ["categoryId"])
    .index("by_name", ["name"]),
});
