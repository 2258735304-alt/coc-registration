import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# --- 配置 ---
DATA_FILE = 'signup_data.csv'  # 本地数据保存文件名


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
def load_data():
    """读取已有的报名数据"""
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=["提交时间", "游戏名字", "大本营等级", "是否接受补位"])


def save_data_to_csv(entry_dict):
    """保存新数据到本地 CSV"""
    df = load_data()
    new_df = pd.DataFrame([entry_dict])
    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
    return df


def append_to_google_sheets(entry_dict):
    """
    尝试把报名信息同步到 Google Sheets。
    依赖：
        - st.secrets["gcp_service_account"]：Google 服务账号 JSON
        - st.secrets["SHEET_ID"]：你的表格 ID
    如果未配置或出错，会给出提示，但不会影响程序正常运行。
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        # 从 Streamlit Secrets 中获取配置
        service_account_info = st.secrets["gcp_service_account"]
        sheet_id = st.secrets["SHEET_ID"]

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1  # 默认第一个工作表

        # 按列顺序存
        row = [
            entry_dict["提交时间"],
            entry_dict["游戏名字"],
            entry_dict["大本营等级"],
            entry_dict["是否接受补位"],
        ]
        sheet.append_row(row)
    except Exception as e:
        # 不中断主流程，只给提示
        st.warning(f"⚠️ 已保存到本地，但同步到 Google 表格时出现问题：{e}")


def create_entry(name, townhall, fill_status):
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

    # 2. 报名表单
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
                    df_new = save_data_to_csv(entry)

                    # 尝试同步到 Google Sheets（如果你配置了 st.secrets）
                    append_to_google_sheets(entry)

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

# --- 管理员/查看区域 (通常放在页面底部) ---
st.markdown("---")
with st.expander("📊 查看已报名名单 (点击展开)"):
    df = load_data()
    if not df.empty:
        # 筛选和搜索
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

        # 提供下载按钮（使用筛选后的数据导出）
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 下载当前筛选结果 (CSV)",
            csv,
            "signup_list_filtered.csv",
            "text/csv",
            key='download-csv'
        )
    else:
        st.write("暂无报名数据。")
