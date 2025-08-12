import streamlit as st
import fitz  # PyMuPDF
import re
import random
import unicodedata

st.set_page_config(page_title="ME2種 出題ツール（PDF限定）", layout="centered")

st.title("ME2種 出題ツール（PDF限定・勝手に作問しない）")
st.caption("※このアプリはアップロードされたPDFの本文だけを使って出題・判定します。推測・作問は一切しません。")

# -------------------- helpers --------------------

def read_pdf_text(pdf_bytes):
    """Extract text per page using PyMuPDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    return texts, doc.page_count

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u3000", " ")
    return s

def detect_round(all_text: str):
    """Detect '第NN回' in the document."""
    m = re.search(r"第\s*(\d+)\s*回", all_text)
    return int(m.group(1)) if m else None

def z2h_num(s: str) -> str:
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    return s.translate(table)

def parse_questions(pages_text):
    """
    抽出ロジック：
      - 見出し：
        ・【問題 １２】 パターン
        ・第12問 パターン（保険）
      - 選択肢：
        ・1）〜5）スタイル
        ・A）〜D）/ ア〜エ スタイル（保険）
    返却: list of {no, stem, options(list), raw_block}
    """
    joined = "\n".join(normalize(t) for t in pages_text)

    # 見出しの候補（全角数字も捕捉）
    pat_square = re.compile(r"【\s*問題\s*([0-9０-９]+)\s*】")
    pat_dai = re.compile(r"第\s*([0-9]+)\s*問")

    # すべての見出しを位置情報込みで収集
    heads = []
    for m in pat_square.finditer(joined):
        heads.append(("sq", int(z2h_num(m.group(1))), m.start(), m.end()))
    for m in pat_dai.finditer(joined):
        heads.append(("dai", int(m.group(1)), m.start(), m.end()))

    heads.sort(key=lambda x: x[2])  # start位置でソート
    if not heads:
        return []

    questions = []
    for i, (kind, qno, start, end) in enumerate(heads):
        block_end = heads[i+1][2] if i+1 < len(heads) else len(joined)
        block = joined[start:block_end].strip()

        # 見出しを除いた本文
        body = joined[end:block_end].strip()

        # 行に分割
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        opts = []
        stem_lines = []

        for ln in lines:
            # 1〜5）
            m1 = re.match(r"^([1-5１-５])\s*[)）.．]\s*(.+)$", ln)
            if m1:
                label = z2h_num(m1.group(1))
                text = m1.group(2).strip()
                opts.append((label, text))
                continue

            # A〜E）保険
            m2 = re.match(r"^([A-EＡ-Ｅ])\s*[)）.．]\s*(.+)$", ln)
            if m2:
                label = m2.group(1)
                mapping = {"Ａ":"A","Ｂ":"B","Ｃ":"C","Ｄ":"D","Ｅ":"E"}
                label = mapping.get(label, label)
                text = m2.group(2).strip()
                opts.append((label, text))
                continue

            # ア〜エ 保険
            m3 = re.match(r"^(ア|イ|ウ|エ)\s*[)）.．]\s*(.+)$", ln)
            if m3:
                kana = m3.group(1)
                mapping = {"ア":"A","イ":"B","ウ":"C","エ":"D"}
                label = mapping[kana]
                text = m3.group(2).strip()
                opts.append((label, text))
                continue

            # どれにもマッチしなければ設問本文
            stem_lines.append(ln)

        # options が抽出できない場合のフォールバック
        if len(opts) == 0:
            tmp = re.split(r"\n(?=[1-5１-５A-EＡ-Ｅア-エ]\s*[)）.．])", body)
            if len(tmp) > 1:
                stem_lines = [tmp[0].strip()]
                for part in tmp[1:]:
                    part = part.strip()
                    m1 = re.match(r"^([1-5１-５])\s*[)）.．]\s*(.+)$", part)
                    if m1:
                        opts.append((z2h_num(m1.group(1)), m1.group(2).strip()))
                    else:
                        m2 = re.match(r"^([A-EＡ-Ｅ])\s*[)）.．]\s*(.+)$", part)
                        if m2:
                            label = m2.group(1)
                            mapping = {"Ａ":"A","Ｂ":"B","Ｃ":"C","Ｄ":"D","Ｅ":"E"}
                            label = mapping.get(label, label)
                            opts.append((label, m2.group(2).strip()))

        stem = "\n".join(stem_lines).strip()

        # ラベル整形（1〜5 → A〜E）※UI表示用
        view_options = []
        for lab, txt in opts[:5]:
            if lab in ["1","2","3","4","5"]:
                lab_view = {"1":"A","2":"B","3":"C","4":"D","5":"E"}[lab]
            else:
                lab_view = lab
            view_options.append((lab_view, txt))

        questions.append({
            "no": qno,
            "stem": stem,
            "options": view_options,   # [("A","..."), ...]
            "raw_block": block
        })

    # ダブり回避
    uniq = {}
    for q in questions:
        uniq[q["no"]] = q
    return [uniq[k] for k in sorted(uniq)]

def parse_answers_from_answers_pdf(pages_text):
    """
    正答PDFから '【問題 12】 4' / '第12問 B' / '12 : 3' などを吸収。
    戻り: {問題番号: 正答(ラベル: "A"〜"E")}
    """
    joined = "\n".join(normalize(t) for t in pages_text)

    mapping_num_to_letter = {"1":"A","2":"B","3":"C","4":"D","5":"E"}
    mapping_kana_to_letter = {"ア":"A","イ":"B","ウ":"C","エ":"D"}
    mapping_full_to_letter = {"Ａ":"A","Ｂ":"B","Ｃ":"C","Ｄ":"D","Ｅ":"E"}

    ans = {}

    # パターン1： 【問題 １２】 4 / 【問題12】 D
    for m in re.finditer(r"【\s*問題\s*([0-9０-９]+)\s*】\s*[:：\s]*([1-5１-５A-EＡ-Ｅア-エ])", joined):
        no = int(z2h_num(m.group(1)))
        val = m.group(2)
        val = z2h_num(val)
        if val in mapping_num_to_letter:
            lab = mapping_num_to_letter[val]
        elif val in mapping_full_to_letter:
            lab = mapping_full_to_letter[val]
        elif val in mapping_kana_to_letter:
            lab = mapping_kana_to_letter[val]
        else:
            lab = val
        ans[no] = lab

    # パターン2： 第12問 A / 第12問 3
    for m in re.finditer(r"第\s*([0-9]+)\s*問\s*[:：\s]*([1-5A-EＡ-Ｅア-エ１-５])", joined):
        no = int(m.group(1))
        val = z2h_num(m.group(2))
        if val in mapping_num_to_letter:
            lab = mapping_num_to_letter[val]
        elif val in mapping_full_to_letter:
            lab = mapping_full_to_letter[val]
        elif val in mapping_kana_to_letter:
            lab = mapping_kana_to_letter[val]
        else:
            lab = val
        ans[no] = lab

    # パターン3： '12 : 3' / '12  D'
    for m in re.finditer(r"\b([0-9]+)\s*[:：\s]\s*([1-5A-EＡ-Ｅア-エ１-５])\b", joined):
        no = int(m.group(1))
        val = z2h_num(m.group(2))
        if val in mapping_num_to_letter:
            lab = mapping_num_to_letter[val]
        elif val in mapping_full_to_letter:
            lab = mapping_full_to_letter[val]
        elif val in mapping_kana_to_letter:
            lab = mapping_kana_to_letter[val]
        else:
            lab = val
        ans[no] = lab

    return ans

def parse_answers_from_tail_of_pm(pm_pages_text, tail_pages=4):
    """問題PDF末尾(数ページ)から正答表を拾う保険。"""
    tail = pm_pages_text[-tail_pages:] if len(pm_pages_text) >= tail_pages else pm_pages_text
    return parse_answers_from_answers_pdf(tail)

# -------------------- UI --------------------

st.subheader("1) PDFをアップロード")
pm_pdf = st.file_uploader("問題PDF（例：44_pm.pdf / 45_am.pdf など）", type=["pdf"], key="pm")
ans_pdf = st.file_uploader("正答PDF（任意・例：44_kaitou.pdf）", type=["pdf"], key="ans")

if pm_pdf is not None:
    with st.spinner("問題PDFを解析中..."):
        pm_pages_text, pm_pages = read_pdf_text(pm_pdf.read())
        questions = parse_questions(pm_pages_text)
        detected_round = detect_round("\n".join(pm_pages_text)) or "不明"

    st.success(f"問題PDF読込完了：{pm_pages}ページ / 検出回：第{detected_round}回")
    st.write(f"抽出できた問題数：{len(questions)}（※PDFの体裁により精度は変わります）")

    # 正答の取得
    answers_map = {}
    ans_source = "未設定"
    if ans_pdf is not None:
        with st.spinner("正答PDFを解析中..."):
            ans_pages_text, _ = read_pdf_text(ans_pdf.read())
            answers_map = parse_answers_from_answers_pdf(ans_pages_text)
            ans_source = "正答PDF"
    else:
        with st.spinner("問題PDF末尾から正答を探索中..."):
            answers_map = parse_answers_from_tail_of_pm(pm_pages_text, tail_pages=4)
            ans_source = "問題PDF末尾ページ"

    if answers_map:
        st.info(f"正答取得：{len(answers_map)}問分 / 出典：{ans_source}")
    else:
        st.warning("正答が抽出できませんでした（判定は不可）。正答PDFのアップロードを推奨します。")

    st.markdown("---")
    st.subheader("2) 出題設定")
    rng_seed = st.number_input("ランダムシード（任意）", min_value=0, max_value=10_000, value=0, step=1)
    only_four = st.checkbox("選択肢が4〜5つ揃っている問題のみ出題", value=True)

    valid_questions = [q for q in questions if (len(q.get("options", [])) >= 2)]
    if only_four:
        valid_questions = [q for q in valid_questions if len(q["options"]) >= 4]

    if len(valid_questions) == 0:
        st.error("出題可能な問題が見つかりません。PDFの体裁または抽出ロジックの調整が必要です。")
        st.stop()

    if st.button("ランダムに1問 出題", use_container_width=True):
        random.seed(rng_seed or None)
        q = random.choice(valid_questions)
        st.session_state["current_q"] = q

    st.markdown("---")
    st.subheader("3) 問題")

    q = st.session_state.get("current_q")
    if q:
        st.write(f"**第{detected_round}回 第{q['no']}問**（出典：問題PDF本文）")
        if q["stem"]:
            st.write(q["stem"])
        else:
            st.caption("（設問本文の抽出に失敗した可能性があります。rawテキストを参照してください）")

        # 選択肢表示
        labels = [lab for lab, _ in q["options"]]
        show_choices = [f"{lab}) {txt}" for lab, txt in q["options"]]
        if show_choices:
            st.write("— 選択肢 —")
            for s in show_choices:
                st.write(s)
        else:
            st.info("選択肢が抽出できていません。本文を確認してください。")

        # 回答入力
        if show_choices:
            user_choice = st.radio("あなたの解答", labels, horizontal=True, key="ans")
        else:
            user_choice = None

        # 正誤判定
        if st.button("解答を判定", use_container_width=True):
            if not answers_map:
                st.error("正答が抽出できていないため、判定できません。正答PDFのアップロードをご検討ください。")
            else:
                correct = answers_map.get(q["no"])
                if correct is None:
                    st.warning("この問題番号の正答が見つかりませんでした。正答PDFを確認してください。")
                else:
                    if user_choice is None:
                        st.info(f"正答は {correct} です（あなたの解答が未選択）。")
                    else:
                        if user_choice == correct:
                            st.success(f"正解！ 正答：{correct}")
                        else:
                            st.error(f"不正解。あなた：{user_choice} / 正答：{correct}")

                    with st.expander("問題ブロック（PDF原文）を表示"):
                        st.text(q["raw_block"])

                    st.caption("※本アプリは“ファイル本文のみ表示”方針のため、解説文の自動生成は行いません。必要に応じてここに任意の解説を追記する欄を設けてください。")

else:
    st.info("問題PDFをアップロードしてください。")
