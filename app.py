import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import io
import time
import shutil
from contextlib import contextmanager

# ================== 基础配置 ==================
DATA_FILE = "signup_data.csv"
EXCEL_FILE = "signup_data.xlsx"
ADMIN_PASSWORD = "52739"

TZ = ZoneInfo("Asia/Shanghai")  # ✅ 统一中国时区

# 管理员强制关闭报名开关（创建文件=关闭）
FORCE_CLOSE_FILE = "force_close.flag"

# 简易文件锁（防并发写）
LOCK_FILE = "signup_data.lock"

# 每次启动自动备份（可按需关掉）
ENABLE_AUTO_BACKUP = True


# ================== 通用工具 ==================
def now_cn() -> datetime:
    return datetime.now(TZ)


def normalize_name(name: str) -> str:
    """规范化名字：去前后空格、压缩中间连续空格"""
    if name is None:
        return ""
    name = name.strip()
    # 将多个空白压成一个
    name = " ".join(name.split())
    return name


def format_countdown(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    d = total // 86400
    h = (total % 86400) // 3600
    m = (total % 3600) // 60
    return f"{d} 天 {h} 小时 {m} 分钟"


def auto_backup():
    """启动时自动备份 CSV，避免误操作/升级导致数据风险"""
    if not ENABLE_AUTO_BACKUP:
        return
    if os.path.exists(DATA_FILE):
        ts = now_cn().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"signup_data_backup_{ts}.csv"
        try:
            shutil.copy(DATA_FILE, backup_name)
        except Exception:
            # 备份失败不影响主流程
            pass


@contextmanager
def file_lock(timeout_seconds: int = 8):
    """
    简易文件锁：通过创建 LOCK_FILE 实现互斥。
    Streamlit Cloud 多用户同时提交时能显著降低写入冲突概率。
    """
    start = time.time()
    while True:
        try:
            # O_EXCL: 若文件存在则报错，达到互斥目的
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - start > timeout_seconds:
                raise TimeoutError("系统繁忙：请稍后再试（写入锁超时）")
            time.sleep(0.12)

    try:
        yield
    finally:
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass


# ================== 时间窗口逻辑 ==================
def get_signup_window(now: datetime | None = None):
    """
    每轮：当月20日 00:00:00 → 次月2日 23:59:59
    自动处理跨月 / 跨年
    """
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


def get_next_signup_start(now: datetime | None = None):
    if now is None:
        now = now_cn()

    if now.day < 20:
        return datetime(now.year, now.month, 20, 0, 0, 0, tzinfo=TZ)

    if now.month == 12:
        return datetime(now.year + 1, 1, 20, 0, 0, 0, tzinfo=TZ)

    return datetime(now.year, now.month + 1, 20, 0, 0, 0, tzinfo=TZ)


def is_signup_open() -> bool:
    if os.path.exists(FORCE_CLOSE_FILE):
        return False
    now = now_cn()
    start, end = get_signup_window(now)
    return start <= now <= end


# ================== 数据层（更稳） ==================
COLUMNS = ["ID", "提交时间", "游戏名字", "大本营等级", "是否接受补位"]


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """保证列齐全 + ID 合法"""
    df = df.copy()
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""

    # ID
    if "ID" not in df.columns or df["ID"].isna().all():
        df.insert(0, "ID", range(1, len(df) + 1))
    df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)

    # 保证列顺序
    df = df[COLUMNS]
    return df


def load_data() -> pd.DataFrame:
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
        except Exception:
            # CSV 读坏了也不至于崩：给空表
            df = pd.DataFrame(columns=COLUMNS)
        return ensure_schema(df)
    return pd.DataFrame(columns=COLUMNS)


def save_full_data(df: pd.DataFrame):
    df = ensure_schema(df)
    # 用锁避免并发写冲突
    with file_lock():
        df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
        # Excel 失败不影响 CSV 主存储
        try:
            df.to_excel(EXCEL_FILE, index=False)
        except Exception:
            pass


def parse_submit_time_series(df: pd.DataFrame) -> pd.Series:
    """
    将“提交时间”解析成带时区的 Series，用于比较当前轮次。
    旧数据通常是无时区字符串，所以要 tz_localize。
    """
    s = pd.to_datetime(df["提交时间"], errors="coerce")
    # s 是 datetime64[ns]（naive），补上海时区
    return s.dt.tz_localize("Asia/Shanghai", nonexistent="shift_forward", ambiguous="NaT")


def add_entry(entry: dict):
    df = load_data()
    next_id = df["ID"].max() + 1 if not df.empty else 1
    entry = {**entry, "ID": int(next_id)}
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    save_full_data(df)


def create_entry(name: str, th: str, fill: str) -> dict:
    return {
        "提交时间": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "游戏名字": name,
        "大本营等级": th,
        "是否接受补位": fill,
    }


# ================== UI ==================
auto_backup()

st.set_page_config(page_title="联赛报名系统", page_icon="⚔️")
st.title("🛡️ 联赛报名系统")
st.markdown("---")

now = now_cn()
current_start, current_end = get_signup_window(now)
next_start = get_next_signup_start(now)

st.caption(
    f"📅 报名规则：每轮从每月 20 日开始，至次月 2 日结束\n"
    f"⏱ 当前轮次：{current_start:%Y-%m-%d} ~ {current_end:%Y-%m-%d}"
)

# ---- 报名区 ----
if is_signup_open():
    st.success("🟢 当前报名通道已开启！")
    st.info(
        f"本轮报名截止：**{current_end:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 距离截止还剩：**{format_countdown(current_end - now)}**"
    )

    with st.form("signup_form"):
        st.subheader("📝 请填写报名信息")

        name_raw = st.text_input("游戏名字", placeholder="例如：部落唐伯虎")
        name = normalize_name(name_raw)

        townhall = st.selectbox("大本营等级", ["18本", "17本", "16本", "16本以下"])
        fill_status = st.radio("是否接受补位", ["补位 (服从安排)", "不补位 (必须首发)"])

        submitted = st.form_submit_button("立即报名")

        if submitted:
            if not name:
                st.error("❌ 请务必填写游戏名字（不能只输入空格）。")
                st.stop()
            if len(name) > 24:
                st.error("❌ 游戏名字太长了（建议 ≤ 24 个字符）。")
                st.stop()

            df_old = load_data()
            duplicated = False
            if not df_old.empty:
                submit_dt = parse_submit_time_series(df_old)
                df_old = df_old.assign(提交时间_dt=submit_dt).dropna(subset=["提交时间_dt"])
                mask_current = df_old["提交时间_dt"].between(current_start, current_end)
                # 用规范化名字做比对，减少空格/大小写导致的“重复漏洞”
                old_names = df_old.loc[mask_current, "游戏名字"].astype(str).map(normalize_name)
                if (old_names == name).any():
                    duplicated = True

            if duplicated:
                st.error("❌ 本轮报名中已存在相同的游戏名字，请勿重复提交。")
            else:
                try:
                    add_entry(create_entry(name, townhall, fill_status))
                    st.balloons()
                    st.success(f"✅ {name}，报名成功！已记录。")
                except TimeoutError as e:
                    st.error(str(e))
else:
    st.error("🔴 当前不在报名时间内。")
    st.info(
        f"📌 下次报名开始时间：**{next_start:%Y-%m-%d %H:%M}**\n\n"
        f"⏳ 距离下次报名还有：**{format_countdown(next_start - now)}**"
    )

# ---- 我的报名记录（你要的）----
st.markdown("---")
with st.expander("🙋 查看我的报名记录（输入游戏名字）", expanded=True):
    df_all = load_data()
    my_name_raw = st.text_input("输入你的游戏名字（会自动忽略前后空格）", key="myname")
    my_name = normalize_name(my_name_raw)

    if my_name and not df_all.empty:
        df_all["提交时间_dt"] = parse_submit_time_series(df_all)
        df_all = df_all.dropna(subset=["提交时间_dt"])

        # 规范化后匹配
        df_all["游戏名字_norm"] = df_all["游戏名字"].astype(str).map(normalize_name)
        mine = df_all[df_all["游戏名字_norm"] == my_name].copy()

        if mine.empty:
            st.warning("没有找到你的记录（确认名字是否完全一致）。")
        else:
            # 本轮 & 历史
            mine_current = mine[mine["提交时间_dt"].between(current_start, current_end)].copy()
            mine_history = mine[~mine.index.isin(mine_current.index)].copy()

            st.subheader("📌 我的本轮记录")
            if mine_current.empty:
                st.write("本轮暂无记录。")
            else:
                st.dataframe(mine_current[COLUMNS], use_container_width=True)

            st.subheader("🗂 我的历史记录")
            if mine_history.empty:
                st.write("暂无历史记录。")
            else:
                st.dataframe(mine_history[COLUMNS], use_container_width=True)
    else:
        st.write("在上面输入游戏名字即可查询。")

# ---- 查看/筛选/下载 + 管理员编辑删除 ----
st.markdown("---")
with st.expander("📊 查看 / 管理已报名名单（筛选、下载、管理员编辑/删除）"):
    df = load_data()

    if df.empty:
        st.write("暂无报名数据。")
    else:
        # 用于显示/筛选
        st.subheader("筛选 / 搜索（查）")

        levels = sorted(df["大本营等级"].dropna().unique().tolist())
        level_selected = st.multiselect("按大本营等级筛选", options=levels, default=levels)

        fills = sorted(df["是否接受补位"].dropna().unique().tolist())
        fill_selected = st.multiselect("按补位意向筛选", options=fills, default=fills)

        name_keyword = st.text_input("按游戏名字搜索（支持模糊匹配）", key="search_name")

        df_display = df.copy()
        if level_selected:
            df_display = df_display[df_display["大本营等级"].isin(level_selected)]
        if fill_selected:
            df_display = df_display[df_display["是否接受补位"].isin(fill_selected)]
        if name_keyword:
            df_display = df_display[
                df_display["游戏名字"].astype(str).str.contains(name_keyword, case=False, na=False)
            ]

        st.dataframe(df_display, use_container_width=True)
        st.caption(f"当前总报名人数：{len(df)} 人（筛选后显示 {len(df_display)} 人）")

        # 下载 CSV/Excel（筛选结果）
        st.subheader("下载（筛选结果）")
        csv_bytes = df_display.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 下载 CSV",
            csv_bytes,
            "signup_list_filtered.csv",
            "text/csv",
            key="download-csv",
        )

        excel_buffer = io.BytesIO()
        df_display.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        st.download_button(
            "📥 下载 Excel",
            excel_buffer,
            "signup_list_filtered.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download-excel",
        )

        st.markdown("---")
        st.subheader("管理员操作（强制关闭 / 修改 / 删除）")

        pwd = st.text_input("输入管理员密码以进行编辑：", type="password", key="admin_pwd")
        if pwd == ADMIN_PASSWORD:
            st.success("✅ 管理员验证通过。")

            # 强制关闭开关
            colA, colB = st.columns(2)
            with colA:
                if os.path.exists(FORCE_CLOSE_FILE):
                    if st.button("▶️ 恢复报名通道"):
                        os.remove(FORCE_CLOSE_FILE)
                        st.success("报名通道已恢复。")
                        st.experimental_rerun()
                else:
                    if st.button("⛔ 强制关闭报名通道"):
                        open(FORCE_CLOSE_FILE, "w").close()
                        st.warning("报名通道已强制关闭。")
                        st.experimental_rerun()

            with colB:
                st.write("（强制关闭仅影响“是否开放报名”，不影响数据查看与下载）")

            # 编辑/删除（对全量数据操作）
            id_options = df_display["ID"].tolist()
            if not id_options:
                st.info("当前筛选结果为空，无法编辑。")
            else:
                selected_id = st.selectbox("选择要修改 / 删除的报名 ID", id_options)

                full_df = load_data()
                row = full_df[full_df["ID"] == selected_id].iloc[0]

                with st.form("edit_delete_form"):
                    st.write(f"当前编辑的记录 ID：**{selected_id}**")

                    edit_name = st.text_input("游戏名字（修改）", value=str(row["游戏名字"]))
                    edit_name = normalize_name(edit_name)

                    townhall_options = ["18本", "17本", "16本", "16本以下"]
                    th_index = townhall_options.index(row["大本营等级"]) if row["大本营等级"] in townhall_options else 0
                    edit_townhall = st.selectbox("大本营等级（修改）", townhall_options, index=th_index)

                    fill_options = ["补位 (服从安排)", "不补位 (必须首发)"]
                    fill_index = fill_options.index(row["是否接受补位"]) if row["是否接受补位"] in fill_options else 0
                    edit_fill = st.radio("是否接受补位（修改）", fill_options, index=fill_index)

                    col1, col2 = st.columns(2)
                    save_btn = col1.form_submit_button("💾 保存修改")
                    delete_btn = col2.form_submit_button("🗑 删除该报名")

                if save_btn or delete_btn:
                    full_df = load_data()
                    if selected_id not in full_df["ID"].values:
                        st.error("未在全量数据中找到该 ID，可能数据已更新，请刷新页面。")
                    else:
                        if save_btn:
                            if not edit_name:
                                st.error("游戏名字不能为空。")
                                st.stop()
                            idx = full_df[full_df["ID"] == selected_id].index[0]
                            full_df.at[idx, "游戏名字"] = edit_name
                            full_df.at[idx, "大本营等级"] = edit_townhall
                            full_df.at[idx, "是否接受补位"] = edit_fill
                            save_full_data(full_df)
                            st.success("✅ 修改已保存。")
                            st.experimental_rerun()

                        if delete_btn:
                            full_df = full_df[full_df["ID"] != selected_id]
                            save_full_data(full_df)
                            st.success("🗑 已删除该报名记录。")
                            st.experimental_rerun()

        elif pwd:
            st.error("❌ 管理员密码错误。")
