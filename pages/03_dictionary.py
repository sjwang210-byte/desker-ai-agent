"""태그 사전 관리 페이지."""

import streamlit as st
import pandas as pd
import io

from core.database import (
    get_connection, get_all_tags, add_tag, add_synonym,
    get_synonyms, get_pending_candidates,
)

st.header("태그 사전 관리")

conn = get_connection()

tab1, tab2, tab3, tab4 = st.tabs(["태그 목록", "동의어 관리", "신규 태그 후보", "가져오기/내보내기"])

# ═══════════════════════════════════════
# 탭 1: 태그 목록
# ═══════════════════════════════════════
with tab1:
    st.subheader("표준 태그 사전")

    # 태그 추가 폼
    with st.expander("새 태그 추가", expanded=False):
        with st.form("add_tag_form"):
            new_tag = st.text_input("태그명")
            new_category = st.text_input("카테고리 (선택사항)", help="예: 상판, 서랍, 다리")
            submitted = st.form_submit_button("추가")
            if submitted and new_tag:
                try:
                    add_tag(conn, new_tag.strip(), new_category.strip() or None)
                    conn.commit()
                    st.success(f"'{new_tag}' 태그가 추가되었습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"추가 실패: {e}")

    # 태그 목록 표시
    tags = get_all_tags(conn, active_only=False)
    if tags:
        df = pd.DataFrame(tags)
        display_cols = ["id", "standard_tag", "category", "is_active", "created_at"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available_cols],
            use_container_width=True,
            column_config={
                "id": "ID",
                "standard_tag": "태그명",
                "category": "카테고리",
                "is_active": st.column_config.CheckboxColumn("활성"),
                "created_at": "생성일",
            },
        )
        st.caption(f"총 {len(tags)}개 태그")
    else:
        st.info("등록된 태그가 없습니다. 위에서 태그를 추가하세요.")

    # 태그 삭제
    if tags:
        with st.expander("태그 비활성화"):
            tag_to_deactivate = st.selectbox(
                "비활성화할 태그",
                [t["standard_tag"] for t in tags if t["is_active"]],
                key="deactivate_tag",
            )
            if st.button("비활성화"):
                conn.execute(
                    "UPDATE tag_dictionary SET is_active = 0 WHERE standard_tag = ?",
                    (tag_to_deactivate,),
                )
                conn.commit()
                st.success(f"'{tag_to_deactivate}' 비활성화 완료.")
                st.rerun()

# ═══════════════════════════════════════
# 탭 2: 동의어 관리
# ═══════════════════════════════════════
with tab2:
    st.subheader("동의어 관리")

    tags = get_all_tags(conn)
    if not tags:
        st.info("먼저 태그를 추가하세요.")
    else:
        selected_tag = st.selectbox(
            "태그 선택",
            tags,
            format_func=lambda t: f"{t['standard_tag']} ({t['category'] or '-'})",
            key="syn_tag_select",
        )

        if selected_tag:
            synonyms = get_synonyms(conn, selected_tag["id"])
            if synonyms:
                st.write("등록된 동의어:")
                for syn in synonyms:
                    st.markdown(f"- {syn}")
            else:
                st.caption("등록된 동의어가 없습니다.")

            # 동의어 추가
            with st.form("add_synonym_form"):
                new_syn = st.text_input("동의어 추가")
                syn_submitted = st.form_submit_button("추가")
                if syn_submitted and new_syn:
                    try:
                        add_synonym(conn, new_syn.strip(), selected_tag["id"])
                        conn.commit()
                        st.success(f"동의어 '{new_syn}' 추가 완료.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"추가 실패: {e}")

# ═══════════════════════════════════════
# 탭 3: 신규 태그 후보
# ═══════════════════════════════════════
with tab3:
    st.subheader("AI 제안 신규 태그 후보")

    candidates = get_pending_candidates(conn)
    if not candidates:
        st.info("대기 중인 신규 태그 후보가 없습니다.")
    else:
        for cand in candidates:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{cand['proposed_text']}**")
                    if cand.get("similar_tag_name"):
                        st.caption(
                            f"유사 태그: {cand['similar_tag_name']} "
                            f"(유사도: {cand.get('similarity_score', 0):.0%})"
                        )
                with col2:
                    if st.button("승인", key=f"approve_{cand['id']}"):
                        tag_id = add_tag(conn, cand["proposed_text"])
                        conn.execute(
                            "UPDATE new_tag_candidates SET status='approved', resolved_at=datetime('now','localtime') WHERE id=?",
                            (cand["id"],),
                        )
                        conn.commit()
                        st.rerun()
                with col3:
                    if st.button("거부", key=f"reject_{cand['id']}"):
                        conn.execute(
                            "UPDATE new_tag_candidates SET status='rejected', resolved_at=datetime('now','localtime') WHERE id=?",
                            (cand["id"],),
                        )
                        conn.commit()
                        st.rerun()

# ═══════════════════════════════════════
# 탭 4: 가져오기/내보내기
# ═══════════════════════════════════════
with tab4:
    st.subheader("사전 가져오기 / 내보내기")

    # 내보내기
    tags = get_all_tags(conn, active_only=False)
    if tags:
        df_export = pd.DataFrame(tags)[["standard_tag", "category", "is_active"]]
        csv_data = df_export.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "CSV 내보내기",
            csv_data,
            file_name="tag_dictionary.csv",
            mime="text/csv",
        )

    # 가져오기
    st.divider()
    uploaded_csv = st.file_uploader("CSV 가져오기", type=["csv"], key="import_csv")
    if uploaded_csv:
        try:
            df_import = pd.read_csv(uploaded_csv)
            st.dataframe(df_import.head())

            if st.button("가져오기 실행"):
                count = 0
                for _, row in df_import.iterrows():
                    tag_name = str(row.get("standard_tag", "")).strip()
                    category = str(row.get("category", "")).strip() or None
                    if category == "nan":
                        category = None
                    if tag_name and tag_name != "nan":
                        try:
                            add_tag(conn, tag_name, category)
                            count += 1
                        except Exception:
                            pass  # 중복 무시
                conn.commit()
                st.success(f"{count}개 태그 가져오기 완료.")
                st.rerun()
        except Exception as e:
            st.error(f"CSV 파싱 오류: {e}")

conn.close()
