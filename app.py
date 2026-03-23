import json
from pathlib import Path
from typing import Any

import streamlit as st


def flatten_json(data: Any, prefix: str = "") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{prefix}.{key}" if prefix else key
            items.extend(flatten_json(value, current_path))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            current_path = f"{prefix}[{index}]"
            items.extend(flatten_json(value, current_path))
    else:
        items.append({"path": prefix, "value": data})

    return items


def tokenize_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    current = ""
    index = 0

    while index < len(path):
        char = path[index]

        if char == ".":
            if current:
                tokens.append(current)
                current = ""
            index += 1
            continue

        if char == "[":
            if current:
                tokens.append(current)
                current = ""
            closing_index = path.find("]", index)
            if closing_index == -1:
                raise ValueError(f"Invalid path: {path}")
            array_token = path[index + 1 : closing_index]
            if not array_token.isdigit():
                raise ValueError(f"Invalid array index in path: {path}")
            tokens.append(int(array_token))
            index = closing_index + 1
            continue

        current += char
        index += 1

    if current:
        tokens.append(current)

    return tokens


def ensure_list_size(items: list[Any], index: int) -> None:
    while len(items) <= index:
        items.append(None)


def insert_path(target: dict[str, Any], path: str, value: Any) -> None:
    tokens = tokenize_path(path)
    if not tokens:
        return

    current: Any = target

    for token_index, token in enumerate(tokens):
        is_last = token_index == len(tokens) - 1
        next_token = tokens[token_index + 1] if not is_last else None

        if isinstance(token, str):
            if not isinstance(current, dict):
                raise ValueError(f"Path conflict at {path}")

            if is_last:
                current[token] = value
                return

            if token not in current or current[token] is None:
                current[token] = [] if isinstance(next_token, int) else {}

            current = current[token]
        else:
            if not isinstance(current, list):
                raise ValueError(f"Path conflict at {path}")

            ensure_list_size(current, token)

            if is_last:
                current[token] = value
                return

            if current[token] is None:
                current[token] = [] if isinstance(next_token, int) else {}

            current = current[token]


def parent_paths_from_leaf_path(leaf_path: str) -> list[str]:
    tokens = tokenize_path(leaf_path)
    if len(tokens) <= 1:
        return []

    parents: list[str] = []
    for end_index in range(1, len(tokens)):
        parent_tokens = tokens[:end_index]
        path_text = ""
        for token in parent_tokens:
            if isinstance(token, str):
                path_text = f"{path_text}.{token}" if path_text else token
            else:
                path_text = f"{path_text}[{token}]"
        parents.append(path_text)

    return parents


def collect_parent_paths(flat_items: list[dict[str, Any]]) -> list[str]:
    parent_set: set[str] = set()
    for item in flat_items:
        for parent in parent_paths_from_leaf_path(item["path"]):
            parent_set.add(parent)
    return sorted(parent_set)


def build_custom_json(selected_paths: list[str], flat_items: list[dict[str, Any]]) -> dict[str, Any]:
    selected_path_set = set(selected_paths)
    selected_map = {
        item["path"]: item["value"]
        for item in flat_items
        if item["path"] in selected_path_set
    }

    result: dict[str, Any] = {}
    for path in selected_paths:
        if path in selected_map:
            insert_path(result, path, selected_map[path])

    return result


def make_output_filename(original_name: str) -> str:
    file_path = Path(original_name)
    if file_path.suffix.lower() == ".json":
        return f"{file_path.stem}+custom.json"
    return f"{file_path.name}+custom.json"


st.set_page_config(page_title="Custom i18n Key Builder", layout="wide")
st.title("Custom i18n Key Builder")
st.caption("Upload JSON → Search/Select keys → Convert → Download file+custom.json")

uploaded_file = st.file_uploader("Upload i18n JSON file", type=["json"])

if uploaded_file is not None:
    try:
        source_data = json.load(uploaded_file)
    except json.JSONDecodeError:
        st.error("ไฟล์ไม่ใช่ JSON ที่ถูกต้อง")
        st.stop()

    if not isinstance(source_data, dict):
        st.error("JSON หลักต้องเป็น object (รูปแบบ key-value)")
        st.stop()

    flat_items = flatten_json(source_data)
    if not flat_items:
        st.warning("ไม่พบ key แบบปลายทาง (leaf keys) ในไฟล์")
        st.stop()

    parent_paths = collect_parent_paths(flat_items)

    search_text = st.text_input(
        "Search by key path or value",
        placeholder="เช่น NICE, SHARED.MAIN.NAME",
    ).strip().lower()

    select_mode = st.radio(
        "Selection mode",
        options=["Leaf keys", "Parent nodes"],
        horizontal=True,
    )

    if search_text:
        filtered_items = [
            item
            for item in flat_items
            if search_text in item["path"].lower() or search_text in str(item["value"]).lower()
        ]
    else:
        filtered_items = flat_items

    st.write(f"Matched keys: {len(filtered_items)}")

    leaf_options = [
        f"{item['path']} = {item['value']}"
        for item in flat_items
    ]
    matched_leaf_options = [
        f"{item['path']} = {item['value']}"
        for item in filtered_items
    ]
    leaf_option_to_path = {
        f"{item['path']} = {item['value']}": item["path"]
        for item in flat_items
    }

    if search_text:
        matched_parent_options = [
            parent_path
            for parent_path in parent_paths
            if search_text in parent_path.lower()
        ]
    else:
        matched_parent_options = parent_paths

    file_identity = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("file_identity") != file_identity:
        st.session_state["file_identity"] = file_identity
        st.session_state["selected_leaf_options"] = []
        st.session_state["selected_parent_options"] = []

    if "selected_leaf_options" not in st.session_state:
        st.session_state["selected_leaf_options"] = []
    if "selected_parent_options" not in st.session_state:
        st.session_state["selected_parent_options"] = []

    control_left, control_right = st.columns(2)
    with control_left:
        if st.button("Select all matched"):
            if select_mode == "Leaf keys":
                current = set(st.session_state["selected_leaf_options"])
                current.update(matched_leaf_options)
                st.session_state["selected_leaf_options"] = sorted(current)
            else:
                current = set(st.session_state["selected_parent_options"])
                current.update(matched_parent_options)
                st.session_state["selected_parent_options"] = sorted(current)
    with control_right:
        if st.button("Clear selection"):
            if select_mode == "Leaf keys":
                st.session_state["selected_leaf_options"] = []
            else:
                st.session_state["selected_parent_options"] = []

    if select_mode == "Leaf keys":
        selected_options = st.multiselect(
            "Select keys to include in custom file",
            options=leaf_options,
            key="selected_leaf_options",
        )
        st.caption(f"Selected leaf keys: {len(selected_options)}")
        selected_paths = [leaf_option_to_path[option] for option in selected_options]
    else:
        selected_parents = st.multiselect(
            "Select parent nodes to include all child keys",
            options=parent_paths,
            key="selected_parent_options",
        )
        st.caption(f"Selected parent nodes: {len(selected_parents)}")
        selected_paths = []
        for item in flat_items:
            path = item["path"]
            if any(path == parent or path.startswith(f"{parent}.") for parent in selected_parents):
                selected_paths.append(path)

    with st.expander("Preview matched results"):
        preview_limit = 200
        if select_mode == "Leaf keys":
            preview_items = matched_leaf_options[:preview_limit]
        else:
            preview_items = matched_parent_options[:preview_limit]

        if preview_items:
            st.write("\n".join(preview_items))
            if (select_mode == "Leaf keys" and len(matched_leaf_options) > preview_limit) or (
                select_mode == "Parent nodes" and len(matched_parent_options) > preview_limit
            ):
                st.caption("แสดงตัวอย่างสูงสุด 200 รายการ")
        else:
            st.write("ไม่พบรายการตามคำค้นหา")

    if st.button("Convert", type="primary"):
        selected_paths = list(dict.fromkeys(selected_paths))

        if not selected_paths:
            st.warning("กรุณาเลือก key อย่างน้อย 1 รายการ")
            st.stop()

        custom_data = build_custom_json(selected_paths, flat_items)
        output_filename = make_output_filename(uploaded_file.name)
        output_json = json.dumps(custom_data, ensure_ascii=False, indent=2)

        st.success("Convert สำเร็จ")
        st.code(output_json, language="json")
        st.download_button(
            label=f"Download {output_filename}",
            data=output_json.encode("utf-8"),
            file_name=output_filename,
            mime="application/json",
        )
else:
    st.info("อัปโหลดไฟล์ i18n JSON เพื่อเริ่มใช้งาน")