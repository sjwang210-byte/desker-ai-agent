"""원인 태깅 & 검수 페이지."""

import streamlit as st
import pandas as pd

from config import HIGH_CONFIDENCE_THRESHOLD, LOW_CONFIDENCE_THRESHOLD
from core.database import (
    get_connection, get_uploaded_months, get_cases_by_month,
    get_untagged_cases, get_all_tags, upsert_case_tag,
    get_case_tags, add_tag, add_new_tag_candidate, record_edit,
)
from core.tag_engine import find_matching_tag, suggest_similar_tags
from core.llm_client import process_cases_in_batches

st.header("원인 태깅")

conn = get_connection()

# ── 월 선택 ──
months = get_uploaded_months(conn)
if not months:
    st.info("먼저 '엑셀 업로드' 페이지에서 데이터를 업로드하세요.")
    st.stop()

selected_month = st.selectbox("월 선택", months)

# ── 현황 표시 ──
all_cases = get_cases_by_month(conn, selected_month)
untagged = get_untagged_cases(conn, selected_month)

col1, col2, col3 = st.columns(3)
col1.metric("총 건수", f"{len(all_cases)}건")
col2.metric("미태깅", f"{len(untagged)}건")
col3.metric("태깅 완료", f"{len(all_cases) - len(untagged)}건")

st.divider()

# ── 자동 태깅 ──
tab_auto, tab_review = st.tabs(["자동 태깅", "건별 검수"])

with tab_auto:
    st.subheader("AI 자동 태깅")

    if not untagged:
        st.success("모든 건이 태깅 완료되었습니다.")
    else:
        st.write(f"미태깅 {len(untagged)}건에 대해 AI 자동 태깅을 실행합니다.")

        if st.button("전체 자동태깅 실행", type="primary"):
            tags = get_all_tags(conn)
            tag_dict = [t["standard_tag"] for t in tags]

            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total):
                progress_bar.progress(current / total)
                status_text.text(f"처리 중... {current}/{total}건")

            try:
                results = process_cases_in_batches(
                    untagged, tag_dict,
                    progress_callback=update_progress,
                )

                # 결과를 DB에 저장
                saved_count = 0
                new_candidate_count = 0

                for result in results:
                    case_id = result.get("db_case_id")
                    if not case_id or result.get("error"):
                        continue

                    for tag_info in result.get("tags", []):
                        tag_text = tag_info.get("tag_text", "").strip()
                        confidence = tag_info.get("confidence", 0.5)
                        is_new = tag_info.get("is_new", False)

                        if not tag_text:
                            continue

                        # 기존 태그 매칭 시도
                        match = find_matching_tag(tag_text, conn)

                        if match:
                            upsert_case_tag(
                                conn, case_id, match["tag_id"],
                                source="ai_proposed",
                                confidence=confidence,
                                ai_raw_text=tag_text,
                                is_final=(confidence >= HIGH_CONFIDENCE_THRESHOLD),
                            )
                            saved_count += 1
                        elif is_new:
                            # 유사 태그 찾기
                            similar = suggest_similar_tags(tag_text, conn, top_n=1)
                            add_new_tag_candidate(
                                conn, tag_text, case_id,
                                similar[0]["tag_id"] if similar else None,
                                similar[0]["similarity"] if similar else None,
                            )
                            new_candidate_count += 1

                conn.commit()
                progress_bar.progress(1.0)
                status_text.text("완료!")

                st.success(
                    f"자동 태깅 완료: {saved_count}개 태그 저장, "
                    f"{new_candidate_count}개 신규 태그 후보 등록"
                )
                st.rerun()

            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"자동 태깅 오류: {e}")

with tab_review:
    st.subheader("건별 검수")

    # 필터
    filter_option = st.radio(
        "필터",
        ["미태깅", "저확신 (검수 필요)", "전체"],
        horizontal=True,
    )

    if filter_option == "미태깅":
        cases_to_show = untagged
    elif filter_option == "저확신 (검수 필요)":
        cases_to_show = []
        for case in all_cases:
            case_tags_list = get_case_tags(conn, case["id"])
            has_low = any(
                (t.get("confidence") or 0) < HIGH_CONFIDENCE_THRESHOLD
                and not t.get("is_final")
                for t in case_tags_list
            )
            if has_low:
                cases_to_show.append(case)
    else:
        cases_to_show = all_cases

    if not cases_to_show:
        st.info("표시할 케이스가 없습니다.")
    else:
        st.caption(f"{len(cases_to_show)}건")

        for case in cases_to_show[:50]:  # 최대 50건 표시
            with st.expander(
                f"#{case['row_number']} | {case.get('product_group', '-')} | "
                f"{(case.get('action_notes') or '-')[:40]}...",
                expanded=False,
            ):
                # 케이스 정보
                st.markdown(f"**품목군:** {case.get('product_group', '-')}")
                st.markdown(f"**제품:** {case.get('product', '-')}")
                st.markdown(f"**판정형태:** {case.get('judgment_type', '-')}")
                st.text_area(
                    "조치결과특이사항",
                    case.get("action_notes", ""),
                    disabled=True,
                    key=f"notes_{case['id']}",
                    height=80,
                )
                st.text_area(
                    "요구내역",
                    case.get("request_details", ""),
                    disabled=True,
                    key=f"req_{case['id']}",
                    height=60,
                )

                # 현재 태그
                current_tags = get_case_tags(conn, case["id"])
                if current_tags:
                    st.markdown("**AI 제안 태그:**")
                    for ct in current_tags:
                        conf = ct.get("confidence", 0) or 0
                        if conf >= HIGH_CONFIDENCE_THRESHOLD:
                            badge = "🟢"
                        elif conf >= LOW_CONFIDENCE_THRESHOLD:
                            badge = "🟡"
                        else:
                            badge = "🔴"
                        final = " ✅" if ct.get("is_final") else ""
                        st.markdown(
                            f"{badge} **{ct['standard_tag']}** "
                            f"(확신도: {conf:.0%}){final}"
                        )

                        # 확인/거부 버튼
                        if not ct.get("is_final"):
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("확인", key=f"confirm_{case['id']}_{ct['tag_id']}"):
                                    upsert_case_tag(
                                        conn, case["id"], ct["tag_id"],
                                        source="user_confirmed",
                                        confidence=1.0,
                                        is_final=True,
                                    )
                                    record_edit(conn, case["id"], ct["tag_id"], "confirm")
                                    conn.commit()
                                    st.rerun()
                            with c2:
                                if st.button("거부", key=f"reject_{case['id']}_{ct['tag_id']}"):
                                    conn.execute(
                                        "DELETE FROM case_tags WHERE case_id=? AND tag_id=?",
                                        (case["id"], ct["tag_id"]),
                                    )
                                    conn.commit()
                                    st.rerun()

                # 수동 태그 추가
                all_tags = get_all_tags(conn)
                if all_tags:
                    with st.form(f"manual_tag_{case['id']}"):
                        manual_tag = st.selectbox(
                            "수동 태그 선택",
                            all_tags,
                            format_func=lambda t: t["standard_tag"],
                            key=f"sel_tag_{case['id']}",
                        )
                        if st.form_submit_button("태그 추가"):
                            upsert_case_tag(
                                conn, case["id"], manual_tag["id"],
                                source="user_confirmed",
                                confidence=1.0,
                                is_final=True,
                            )
                            record_edit(conn, case["id"], manual_tag["id"], "add")
                            conn.commit()
                            st.rerun()

conn.close()
