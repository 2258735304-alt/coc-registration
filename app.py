import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import io
import shutil

# 基础配置
DATA_FILE = "signup_data.csv"
EXCEL_FILE = "signup_data.xlsx"
ADMIN_PASSWORD = "52739"

TZ = ZoneInfo("Asia/Shanghai")  # 中国时区
FORCE_CLOSE_FILE = "force_close.flag"  # 管理员强制关闭标记


# 通用工具
def now_cn():
    return datetime.now(TZ)


def auto_backup():
    """启动时自动备份 CSV（一天多次启动也安全）"""
    if os.path.exists(DATA_FILE):
        ts = now_cn().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"signup_data_backup_{ts}.csv"
        shutil.copy(DATA_FILE, backup_name)


# 时间窗口
def get_signup_window(now=None):
    if now is None:
        now = now_cn()

    y, m, d = now.year, now.month, now.day

    if d >= 20:
        start = datetime(y, m, 20, 0, 0, 0, tzinfo=TZ)
        if m == 12:
            end = datetime(y + 1, 1, 2, 23, 59, 59, tzinfo=TZ)
        else:
            end = datetime(y, m + 1, 2, 23, 59, 59, tzinfo=TZ)
    else:
        if m == 1:
            start = datetime(y - 1, 12, 20, 0, 0, 0, tzinfo=TZ)
        else:
            start = datetime(y, m - 1, 20, 0, 0, 0, tzinfo=TZ)
        end = datetime(y, m, 2, 23, 59, 59, tzinfo=TZ)

    return start, end


def is_signup_open():
    if os.path.exists(FORCE_CLOSE_FILE):
        return False
    now = now_cn()
    start, end = get_signup_window(now)
    return start <= now <= end


def get_next_signup_start(now=None):
    if now is None:
        now = now_cn()

    if now.day < 20:
        return datetime(now.year, now.month, 20, 0, 0, 0, tzinfo=TZ)
    else:
        if now.month == 12:
            return datetime(now.year + 1, 1, 20, 0, 0, 0, tzinfo=TZ)
        else:
            return datetime(now.year, now.month + 1, 20, 0, 0, 0, tzinfo=TZ)


def format_countdown(td: timedelta):
    total = max(0, int(td.total_seconds()))
    d = total // 86400
    h = (total % 86400) // 3600
    m = (total % 3600) // 60
    return f"{d} 天 {h} 小时 {m} 分钟"


# 数据处理
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


def create_entry(name, th, fill):
    return {
        "提交时间": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "游戏名字": name,
        "大本营等级": th,
        "是否接受补位": fill,
    }


# 页面
auto_backup()

st.set_page_config("联赛报名系统", "⚔️")
st.title("🛡️ 联赛报名系统")
st.markdown("---")

now = now_cn()
current_start, current_end = get_signup_window(now)
next_start = get_next_signup_start(now)

st.caption(
    f"📅 报名规则：每月20日 → 次月2日\n"
    f"⏱ 当前轮次：{current_start:%Y-%m-%d} ~ {current_end:%Y-%m-%d}"
)

if is_signup_open():
    st.success("🟢 当前报名通道已开启")
    st.info(
        f"截止时间：**{current_end:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 剩余：**{format_countdown(current_end - now)}**"
    )

    with st.form("signup"):
        name = st.text_input("游戏名字")
        th = st.selectbox("大本营等级", ["18本", "17本", "16本", "16本以下"])
        fill = st.radio("是否接受补位", ["补位 (服从安排)", "不补位 (必须首发)"])
        submit = st.form_submit_button("立即报名")

        if submit:
            if not name:
                st.error("请填写游戏名字")
            else:
                df = load_data()
                if not df.empty:
                    df["提交时间_dt"] = (
                        pd.to_datetime(df["提交时间"], errors="coerce")
                        .dt.tz_localize("Asia/Shanghai")
                    )
                    df = df.dropna(subset=["提交时间_dt"])
                    mask = df["提交时间_dt"].between(current_start, current_end)
                    if (df.loc[mask, "游戏名字"] == name).any():
                        st.error("本轮已报名，请勿重复提交")
                        st.stop()

                add_entry(create_entry(name, th, fill))
                st.success("报名成功 🎉")
                st.balloons()
else:
    st.error("🔴 当前不在报名时间内")
    st.info(
        f"📌 下次开始：**{next_start:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 剩余：**{format_countdown(next_start - now)}**"
    )

# 管理员
st.markdown("---")
with st.expander("🔐 管理员控制"):
    pwd = st.text_input("管理员密码", type="password")
    if pwd == ADMIN_PASSWORD:
        if os.path.exists(FORCE_CLOSE_FILE):
            if st.button("▶️ 恢复报名通道"):
                os.remove(FORCE_CLOSE_FILE)
                st.success("报名通道已恢复")
                st.experimental_rerun()
        else:
            if st.button("⛔ 强制关闭报名"):
                open(FORCE_CLOSE_FILE, "w").close()
                st.warning("报名已被强制关闭")
                st.experimental_rerun()
