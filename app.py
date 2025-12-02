import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- 配置 ---
DATA_FILE = 'signup_data.csv'  # 数据保存的文件名


# --- 功能函数 ---
def is_signup_open():
    """
    检查当前是否在报名时间内。
    规则：每月20日开始，到次月1日截止。
    """
    today = datetime.now()
    day = today.day

    # 逻辑：如果在20号以后(含20)，或者在1号(含1)，则为开放时间
    if day >= 20 or day <= 1:
        return True
    return False


def load_data():
    """读取已有的报名数据"""
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=["提交时间", "游戏名字", "大本营等级", "是否接受补位"])


def save_data(name, townhall, fill_status):
    """保存新数据"""
    new_entry = {
        "提交时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "游戏名字": name,
        "大本营等级": townhall,
        "是否接受补位": fill_status
    }
    df = load_data()
    # 使用 concat 替代 append (pandas 新版特性)
    new_df = pd.DataFrame([new_entry])
    df = pd.concat([df, new_df], ignore_index=True)
    # 原代码: df.to_csv(DATA_FILE, index=False)
    # 修改为:
    df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
    return df


# --- 网页界面设计 ---
st.set_page_config(page_title="联赛报名系统", page_icon="⚔️")

st.title("🛡️ 联赛报名系统")
st.markdown("---")

# 1. 检查时间
if is_signup_open():
    st.success(f"🟢 当前通道已开启！(每月20日 - 次月1日)")

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
                save_data(name, townhall, fill_status)
                st.balloons()  # 撒花特效
                st.success(f"✅ {name}，报名成功！已记录。")

else:
    st.error("🔴 当前不在报名时间内。")
    st.info("报名时间为：每月 20 日 至 次月 1 日。请届时再来。")

# --- 管理员/查看区域 (通常放在页面底部) ---
st.markdown("---")
with st.expander("📊 查看已报名名单 (点击展开)"):
    df = load_data()
    if not df.empty:
        st.dataframe(df)
        st.caption(f"当前总报名人数: {len(df)} 人")

        # 提供下载按钮
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 下载报名表(CSV)",
            csv,
            "signup_list.csv",
            "text/csv",
            key='download-csv'
        )
    else:
        st.write("暂无报名数据。")

