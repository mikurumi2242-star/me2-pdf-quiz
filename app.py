import streamlit as st
import json, os, random

st.set_page_config(page_title="ME2種：起動で1問", layout="centered")
st.title("ME2種：今日の1問")
st.caption("data/*.json の内容だけを使用します。アップロードや生成は行いません。")

DATA_DIR = "data"

@st.cache_data
def load_all_questions():
    items = []
    if not os.path.isdir(DATA_DIR):
        return items
  for fn in os.listdir(DATA_DIR):
        if fn.lower().endswith(".json"):
            path = os.path.join(DATA_DIR, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                for q in arr:
                    opts = q.get("options") or []
                    ans  = q.get("answer")
                    # 5択固定＆正答は1〜5
                    if len(opts) != 5: 
                        continue
                    if ans not in ["1","2","3","4","5"]:
                        continue
                    items.append(q)
            except Exception as e:
                print("load fail", fn, e)
    return items

qs = load_all_questions()
if not qs:
    st.error("問題データがありません。data/pool.json に問題を入れてください。")
    st.stop()

# 起動と同時にランダム1問（リロードで変わる）
if "current" not in st.session_state:
    st.session_state.current = random.choice(qs)

q = st.session_state.current
labels = ["A","B","C","D","E"][:len(q["options"])]

st.subheader(f"第{q.get('round','?')}回 {q.get('part','?')} / 第{q.get('no','?')}問")
st.write(q["stem"])

st.write("— 選択肢 —")
for lab, txt in zip(labels, q["options"]):
    st.write(f"{lab}) {txt}")

user = st.radio("あなたの解答", labels, horizontal=True, index=None, key="ans")

col1, col2 = st.columns(2)
with col1:
    if st.button("解答を判定", use_container_width=True):
        if user is None:
            st.warning("選択肢を選んでから判定してください。")
        else:
            if user == q["answer"]:
                st.success(f"正解！ 正答：{q['answer']}")
            else:
                st.error(f"不正解… 正答：{q['answer']} / あなた：{user}")

with col2:
    if st.button("次の問題（ランダム）", use_container_width=True):
        st.session_state.current = random.choice(qs)
        st.session_state.ans = None
        st.rerun()
