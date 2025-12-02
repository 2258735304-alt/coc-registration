import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io

# --- 配置 ---
DATA_FILE = 'signup_data.csv'   # 本地 CSV 文件名
EXCEL_FILE = 'signup_data.xlsx' # 本地 Excel 文件名
ADMIN_PASSWORD = "52739"       # 管理员密码（你可以自己改）


# --- 时间窗口相关函数 ---
def get_signup_window(now=None):
    """
    返回当前“这轮报名”的起止时间（自动处理跨月 / 跨年）：
    每轮规则：每月20日开始，到次月2日 23:59:59 截止。
    例如：
    - 2024-12-20 ~ 2025-01-02
    - 2025-01-20 ~ 2025-02-02
    """
    if now is None:
        now = datetime.now()

    year = now.year
    month = now.month
    day = now.day

    # 如果今天是 20~31 号，则属于“本月20 ~ 下月2”这一轮
    if day >= 20:
        start = datetime(year, month, 20, 0, 0, 0)
        # 计算下月
        if month == 12:
            end = datetime(year + 1, 1, 2, 23, 59, 59)
        else:
            end = datetime(year, month + 1, 2, 23, 59, 59)
    else:
        # 今天是 1~19 号，则属于“上月20 ~ 本月2”这一轮
        if month == 1:
            start = datetime(year - 1, 12, 20, 0, 0, 0)
        else:
            start = datetime(year, month - 1, 20, 0, 0, 0)
        end = datetime(year, month, 2, 23, 59, 59)

    return start, end


def is_signup_open():
    """
    当前时间是否在报名窗口内（含跨年情况）。
    规则：每轮为“20 日 00:00:00 ~ 次月 2 日 23:59:59”。
    """
    now = datetime.now()
    start, end = get_signup_window(now)
    return start <= now <= end


def get_next_signup_start(now=None):
    """
    返回“下一轮报名”的开始时间（每月20日），用于提前显示。
    即使当前就在报名窗口内，也会给出“下一轮”的 20 号。
    """
    if now is None:
        now = datetime.now()

    year = now.year
    month = now.month
    day = now.day

    # 如果今天小于20号，那么下一轮从本月20号开始
    if day < 20:
        start_month = month
        start_year = year
    else:
        # 否则下一轮从下个月20号开始（自动跨年）
        if month == 12:
            start_year = year + 1
            start_month = 1
        else:
            start_year = year
            start_month = month + 1

    return datetime(start_year, start_month, 20, 0, 0, 0)


# --- 数据相关函数 ---
def ensure_id_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    保证数据里有 ID 字段：
    - 如果没有 ID，就自动从 1 开始编号
    - 如果有 ID，就保持不变
    """
    if "ID" not in df.columns:
        # 新增 ID 列放在最前面
        df = df.copy()
        df.insert(0, "ID", range(1, len(df) + 1))
    else:
        # 确保 ID 是整数
        df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
    return df


def load_data() -> pd.DataFrame:
    """读取已有的报名数据，并保证有 ID 列"""
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df = ensure_id_column(df)
        # 同步回文件，避免旧数据没有 ID
        save_full_data(df)
        return df
    else:
        df = pd.DataFrame(columns=["ID", "提交时间", "游戏名字", "大本营等级", "是否接受补位"])
        return df


def save_full_data(df: pd.DataFrame):
    """将整张表一次性写回 CSV 和 Excel"""
    df = ensure_id_column(df)
    df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
    df.to_excel(EXCEL_FILE, index=False)


def add_entry(entry_dict: dict) -> pd.DataFrame:
    """新增一条报名记录（增）"""
    df = load_data()
    df = ensure_id_column(df)

    if df.empty:
        next_id = 1
    else:
        next_id = df["ID"].max() + 1

    entry_with_id = {
        "ID": next_id,
        **entry_dict
    }

    new_df = pd.DataFrame([entry_with_id])
    df = pd.concat([df, new_df], ignore_index=True)
    save_full_data(df)
    return df


def create_entry(name, townhall, fill_status) -> dict:
    """构造一个报名记录字典，便于复用"""
    return {
        "提交时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "游戏名字": name,
        "大本营等级": townhall,
        "是否接受补位": fill_status
    }


# --- 网页界面设计 ---
st.set_page_config(page_title="联赛报名系统", page_icon="⚔️")

st.title("🛡️ 联赛报名系统")
st.markdown("---")

now = datetime.now()
current_start, current_end = get_signup_window(now)
next_start = get_next_signup_start(now)

# 友好的报名时间信息
st.caption(
    f"📅 当前报名规则：每轮从每月 20 日 开始，至 次月 2 日 结束。\n"
    f"⏱ 当前这一轮的时间区间：{current_start.strftime('%Y-%m-%d')} ~ {current_end.strftime('%Y-%m-%d')}"
)

# 1. 检查时间 + 倒计时展示
if is_signup_open():
    # 距离本轮结束的倒计时
    remaining = current_end - now
    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60

    st.success("🟢 当前报名通道已开启！")
    st.info(
        f"本轮报名截止时间：**{current_end.strftime('%Y-%m-%d %H:%M')}**  \n"
        f"⏳ 距离截止还剩：**{days} 天 {hours} 小时 {minutes} 分钟**"
    )

    # 2. 报名表单（增）
    with st.form("signup_form"):
        st.subheader("📝 请填写报名信息")

        name = st.text_input("游戏名字", placeholder="例如：COC战神")

        # 16-18本选择
        townhall = st.selectbox("大本营等级", ["18本", "17本", "16本", "16本以下"])

        # 补位选择
        fill_status = st.radio("是否接受补位", ["补位 (服从安排)", "不补位 (必须首发)"])

        submitted = st.form_submit_button("立即报名")

        if submitted:
            if not name:
                st.error("❌ 请务必填写游戏名字！")
            else:
                # 重复报名检查：同一轮，同一游戏名字只允许一次
                df_old = load_data()
                duplicated = False
                if not df_old.empty:
                    df_old_tmp = df_old.copy()
                    df_old_tmp["提交时间_dt"] = pd.to_datetime(
                        df_old_tmp["提交时间"], errors="coerce"
                    )
                    mask_current = df_old_tmp["提交时间_dt"].between(current_start, current_end)
                    if (df_old_tmp.loc[mask_current, "游戏名字"] == name).any():
                        duplicated = True

                if duplicated:
                    st.error("❌ 本轮报名中已存在相同的游戏名字，请勿重复提交。")
                else:
                    entry = create_entry(name, townhall, fill_status)
                    df_new = add_entry(entry)

                    st.balloons()
                    st.success(f"✅ {name}，报名成功！已记录。")
else:
    st.error("🔴 当前不在报名时间内。")
    # 下一轮信息 + 倒计时
    diff = next_start - now
    days_to_next = diff.days
    st.info(
        f"📌 下次报名开始时间：**{next_start.strftime('%Y-%m-%d %H:%M')}**  \n"
        f"⏳ 距离下次报名还有：**{days_to_next} 天左右**"
    )

# --- 管理员/查看区域 (查 / 改 / 删) ---
st.markdown("---")
with st.expander("📊 查看 / 管理已报名名单 (点击展开)"):
    df = load_data()
    if not df.empty:
        # 筛选和搜索（查）
        st.subheader("筛选 / 搜索")

        # 按大本营等级筛选
        levels = sorted(df["大本营等级"].dropna().unique().tolist())
        level_selected = st.multiselect(
            "按大本营等级筛选",
            options=levels,
            default=levels
        )

        # 按补位意向筛选
        fills = sorted(df["是否接受补位"].dropna().unique().tolist())
        fill_selected = st.multiselect(
            "按补位意向筛选",
            options=fills,
            default=fills
        )

        # 按名字搜索
        name_keyword = st.text_input("按游戏名字搜索（支持模糊匹配）")

        df_display = df.copy()

        if level_selected:
            df_display = df_display[df_display["大本营等级"].isin(level_selected)]
        if fill_selected:
            df_display = df_display[df_display["是否接受补位"].isin(fill_selected)]
        if name_keyword:
            df_display = df_display[
                df_display["游戏名字"].astype(str).str.contains(
                    name_keyword, case=False, na=False
                )
            ]

        st.dataframe(df_display)
        st.caption(f"当前总报名人数: {len(df)} 人（筛选后显示 {len(df_display)} 人）")

        # 下载 CSV
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 下载当前筛选结果 (CSV)",
            csv,
            "signup_list_filtered.csv",
            "text/csv",
            key='download-csv'
        )

        # 下载 Excel
        excel_buffer = io.BytesIO()
        df_display.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)

        st.download_button(
            "📥 下载当前筛选结果 (Excel)",
            excel_buffer,
            "signup_list_filtered.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key='download-excel'
        )

        st.markdown("---")
        st.subheader("管理员操作（修改 / 删除）")

        # 管理员验证
        pwd = st.text_input("输入管理员密码以进行编辑（默认 123456，可在代码开头修改）", type="password")
        if pwd == ADMIN_PASSWORD:
            st.success("✅ 管理员验证通过，可进行编辑操作。")

            if not df_display.empty:
                # 选择要编辑的 ID
                id_options = df_display["ID"].tolist()
                selected_id = st.selectbox("选择要修改 / 删除的报名 ID", id_options)

                row = df_display[df_display["ID"] == selected_id].iloc[0]

                with st.form("edit_delete_form"):
                    st.write(f"当前编辑的记录 ID：**{selected_id}**")

                    edit_name = st.text_input("游戏名字（修改）", value=row["游戏名字"])

                    townhall_options = ["18本", "17本", "16本", "16本以下"]
                    if row["大本营等级"] in townhall_options:
                        th_index = townhall_options.index(row["大本营等级"])
                    else:
                        th_index = 0
                    edit_townhall = st.selectbox(
                        "大本营等级（修改）",
                        townhall_options,
                        index=th_index
                    )

                    fill_options = ["补位 (服从安排)", "不补位 (必须首发)"]
                    if row["是否接受补位"] in fill_options:
                        fill_index = fill_options.index(row["是否接受补位"])
                    else:
                        fill_index = 0
                    edit_fill = st.radio(
                        "是否接受补位（修改）",
                        fill_options,
                        index=fill_index
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        save_btn = st.form_submit_button("💾 保存修改")
                    with col2:
                        delete_btn = st.form_submit_button("🗑 删除该报名")

                # 重新从全量数据操作，避免只在筛选结果上改
                if save_btn or delete_btn:
                    full_df = load_data()
                    full_df = ensure_id_column(full_df)

                    if selected_id not in full_df["ID"].values:
                        st.error("未在全量数据中找到该 ID，可能数据已更新，请刷新页面。")
                    else:
                        if save_btn:
                            # 修改
                            idx = full_df[full_df["ID"] == selected_id].index[0]
                            full_df.at[idx, "游戏名字"] = edit_name
                            full_df.at[idx, "大本营等级"] = edit_townhall
                            full_df.at[idx, "是否接受补位"] = edit_fill
                            save_full_data(full_df)
                            st.success("✅ 修改已保存。请刷新页面查看最新数据。")
                            st.experimental_rerun()

                        if delete_btn:
                            # 删除
                            full_df = full_df[full_df["ID"] != selected_id]
                            save_full_data(full_df)
                            st.success("🗑 已删除该报名记录。")
                            st.experimental_rerun()
        elif pwd:
            st.error("❌ 管理员密码错误。")
    else:
        st.write("暂无报名数据。")

