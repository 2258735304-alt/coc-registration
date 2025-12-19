import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import io

# ================== 基础配置 ==================
DATA_FILE = 'signup_data.csv'
EXCEL_FILE = 'signup_data.xlsx'
ADMIN_PASSWORD = "52739"

TZ = ZoneInfo("Asia/Shanghai")  # ✅ 统一中国时区


# ================== 时间工具函数 ==================
def now_cn():
    return datetime.now(TZ)


def get_signup_window(now=None):
    """
    每轮：当月20日 00:00:00 → 次月2日 23:59:59
    自动处理跨月 / 跨年
    """
    if now is None:
        now = now_cn()

    year, month, day = now.year, now.month, now.day

    if day >= 20:
        start = datetime(year, month, 20, 0, 0, 0, tzinfo=TZ)
        if month == 12:
            end = datetime(year + 1, 1, 2, 23, 59, 59, tzinfo=TZ)
        else:
            end = datetime(year, month + 1, 2, 23, 59, 59, tzinfo=TZ)
    else:
        if month == 1:
            start = datetime(year - 1, 12, 20, 0, 0, 0, tzinfo=TZ)
        else:
            start = datetime(year, month - 1, 20, 0, 0, 0, tzinfo=TZ)
        end = datetime(year, month, 2, 23, 59, 59, tzinfo=TZ)

    return start, end


def is_signup_open():
    now = now_cn()
    start, end = get_signup_window(now)
    return start <= now <= end


def get_next_signup_start(now=None):
    if now is None:
        now = now_cn()

    year, month, day = now.year, now.month, now.day

    if day < 20:
        return datetime(year, month, 20, 0, 0, 0, tzinfo=TZ)
    else:
        if month == 12:
            return datetime(year + 1, 1, 20, 0, 0, 0, tzinfo=TZ)
        else:
            return datetime(year, month + 1, 20, 0, 0, 0, tzinfo=TZ)


def format_countdown(td: timedelta):
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    return f"{days} 天 {hours} 小时 {minutes} 分钟"


# ================== 数据函数 ==================
def ensure_id_column(df):
    if "ID" not in df.columns:
        df.insert(0, "ID", range(1, len(df) + 1))
    df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
    return df


def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        return ensure_id_column(df)
    return pd.DataFrame(columns=["ID", "提交时间", "游戏名字", "大本营等级", "是否接受补位"])


def save_full_data(df):
    df = ensure_id_column(df)
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    df.to_excel(EXCEL_FILE, index=False)


def add_entry(entry):
    df = load_data()
    next_id = df["ID"].max() + 1 if not df.empty else 1
    entry["ID"] = next_id
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    save_full_data(df)


def create_entry(name, townhall, fill):
    return {
        "提交时间": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "游戏名字": name,
        "大本营等级": townhall,
        "是否接受补位": fill
    }


# ================== 页面 ==================
st.set_page_config("联赛报名系统", "⚔️")
st.title("🛡️ 联赛报名系统")
st.markdown("---")

now = now_cn()
current_start, current_end = get_signup_window(now)
next_start = get_next_signup_start(now)

st.caption(
    f"📅 报名规则：每月 20 日开始，至次月 2 日结束\n"
    f"⏱ 当前轮次：{current_start:%Y-%m-%d} ~ {current_end:%Y-%m-%d}"
)

if is_signup_open():
    st.success("🟢 当前报名通道已开启")
    st.info(
        f"截止时间：**{current_end:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 剩余时间：**{format_countdown(current_end - now)}**"
    )

    with st.form("signup"):
        name = st.text_input("游戏名字")
        townhall = st.selectbox("大本营等级", ["18本", "17本", "16本", "16本以下"])
        fill = st.radio("是否接受补位", ["补位 (服从安排)", "不补位 (必须首发)"])
        submit = st.form_submit_button("立即报名")

        if submit:
            if not name:
                st.error("请填写游戏名字")
            else:
                df = load_data()
               df["提交时间_dt"] = pd.to_datetime(
    df["提交时间"],
    errors="coerce"
).dt.tz_localize("Asia/Shanghai")  # ✅ 关键：补上时区

mask = df["提交时间_dt"].between(current_start, current_end)

                if (df.loc[mask, "游戏名字"] == name).any():
                    st.error("本轮已报名，请勿重复提交")
                else:
                    add_entry(create_entry(name, townhall, fill))
                    st.success("报名成功 🎉")
                    st.balloons()
else:
    st.error("🔴 当前不在报名时间内")
    st.info(
        f"📌 下次开始时间：**{next_start:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 剩余时间：**{format_countdown(next_start - now)}**"
    )

