#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心理健康课程视频自动连播：打开课程页 → 人工登录并进入视频页 → 回车后开始循环播放/检测进度/下一节。

运行（conda 环境名：auto）：
  conda activate auto && pip install -r requirements.txt && python course_autoplay.py
  或在本目录执行：./run.sh
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    NoSuchWindowException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 课程入口（来自 PRD）
COURSE_URL = (
    "https://smartcourse.hust.edu.cn/mooc2-ans/mooc2-ans/mycourse/stu"
    "?courseid=17310000022966&clazzid=17310000017957&cpi=17310000158138"
    "&enc=aee62e8272614c543b585c3dd58ceec4&t=1776855970261&pageHeader=1"
)

# PRD 中的 XPath（页面结构变化时需自行替换）
XPATH_PLAY = "/html/body/div[2]/div[1]/div[3]/div[2]/div/button"
# 监测是否播完：对比当前时间与总时长（与 PRD 一致）
XPATH_CURRENT_TIME = "/html/body/div[2]/div[1]/div[3]/div[2]/div/div[6]/div[2]/span[2]"
XPATH_TOTAL_TIME = "/html/body/div[2]/div[1]/div[3]/div[2]/div/div[6]/div[4]/span[2]"
XPATH_NEXT = "/html/body/div[6]/div/div[3]/div[8]/div[1]"
# 若出现则点击（如弹层确认），不存在则忽略（PRD）
XPATH_OPTIONAL_ACK = "/html/body/div[6]/div/div[3]/div[1]/div/div[3]/a[2]"

# 单节视频最长等待（秒），防止异常时死循环
MAX_SECTION_SECONDS = 3 * 60 * 60
# 轮询进度间隔（秒）
POLL_INTERVAL = 2.0


def _try_switch_to_context_having(driver: webdriver.Chrome, by: str, value: str) -> bool:
    """
    从默认文档起深度优先进入 iframe/frame，切到首个能匹配定位器的文档。
    课程页视频控件常在子 frame 内，仅用顶层 XPath 会超时。
    """
    driver.switch_to.default_content()

    def dfs() -> bool:
        try:
            if driver.find_elements(by, value):
                return True
        except NoSuchWindowException:
            return False
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        for i in range(len(frames)):
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            if i >= len(frames):
                break
            try:
                driver.switch_to.frame(frames[i])
            except NoSuchWindowException:
                continue
            if dfs():
                return True
            try:
                driver.switch_to.parent_frame()
            except NoSuchWindowException:
                driver.switch_to.default_content()
        return False

    return dfs()


def _native_click(driver: webdriver.Chrome, el) -> None:
    """使用 Selenium 推荐的可见交互：滚动到视区 + ActionChains 点击（非 JS 合成 click）。"""
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            try:
                ActionChains(driver).scroll_to_element(el).move_to_element(el).pause(0.08).click(el).perform()
            except AttributeError:
                # 极旧版无 scroll_to_element，仅辅助滚动，点击仍走 ActionChains
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                    el,
                )
                time.sleep(0.08)
                ActionChains(driver).move_to_element(el).pause(0.08).click(el).perform()
            return
        except (ElementClickInterceptedException, StaleElementReferenceException) as exc:
            last_exc = exc
            time.sleep(0.35)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.2)
    if last_exc:
        raise last_exc


def _prepare_target_tab(driver: webdriver.Chrome) -> None:
    """
    多标签 / 关标签后对齐 WebDriver 与真实页面。

    Selenium 的「当前窗口」不会随你在浏览器里点到哪个标签而自动切换；若脚本曾切到
    window_handles 里「最后一个」标签，而你关掉的正是它，就会报 target window already closed。
    因此在回车后：在仍存在的标签中优先切换到能检测到播放按钮的那一页。
    """
    handles = list(driver.window_handles)
    if not handles:
        raise RuntimeError("浏览器中已没有可用标签页，请打开课程视频页后重新运行。")

    for h in handles:
        try:
            driver.switch_to.window(h)
        except NoSuchWindowException:
            continue
        try:
            if _try_switch_to_context_having(driver, By.XPATH, XPATH_PLAY):
                return
        except NoSuchWindowException:
            pass
        driver.switch_to.default_content()

    # 句柄列表可能已变（关标签过程中），再取一次并挂到仍存在的最后一页，避免指向已关闭页
    remaining = list(driver.window_handles)
    if not remaining:
        raise RuntimeError("切换标签时所有窗口已关闭，请重新打开视频页后运行。")
    driver.switch_to.window(remaining[-1])
    driver.switch_to.default_content()


def _major_from_version_output(text: str) -> int | None:
    """从 `Google Chrome 147.x` 或 `ChromeDriver 144.x` 类输出中取主版本号。"""
    m = re.search(r"(?:Chrome|ChromeDriver)\s+(\d+)\.", text)
    if m:
        return int(m.group(1))
    return None


def _major_from_cmd(cmd: list[str]) -> int | None:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=8)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return _major_from_version_output(out)


def _detect_chrome_binary() -> str | None:
    """尽量定位本机 Chrome/Chromium 可执行文件路径。"""
    if sys.platform == "darwin":
        mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(mac).is_file():
            return mac
    for name in ("google-chrome-stable", "google-chrome", "chrome", "chromium"):
        w = shutil.which(name)
        if w:
            return w
    return None


def _browser_major() -> int | None:
    exe = _detect_chrome_binary()
    if not exe:
        return None
    return _major_from_cmd([exe, "--version"])


def _build_chrome_service() -> Service:
    """
    解析 ChromeDriver，避免 Selenium Manager 在无法联网时使用过旧缓存导致主版本不一致。
    优先级：CHROMEDRIVER_PATH → PATH 中主版本匹配的 chromedriver → webdriver-manager。
    """
    explicit = os.environ.get("CHROMEDRIVER_PATH", "").strip()
    if explicit:
        exp = Path(explicit).expanduser()
        if exp.is_file():
            return Service(str(exp))
        raise FileNotFoundError(f"CHROMEDRIVER_PATH 不是有效文件：{explicit}")

    browser_maj = _browser_major()
    which = shutil.which("chromedriver")
    if which:
        drv_maj = _major_from_cmd([which, "--version"])
        if browser_maj is None or drv_maj is None or drv_maj == browser_maj:
            return Service(which)
        print(
            f"[提示] PATH 中 chromedriver 主版本为 {drv_maj}，Chrome 为 {browser_maj}，将尝试自动下载匹配驱动…",
            file=sys.stderr,
        )

    try:
        from webdriver_manager.chrome import ChromeDriverManager

        return Service(ChromeDriverManager().install())
    except Exception as exc:
        plat = platform.system()
        extra = ""
        if plat == "Darwin":
            extra = "macOS 可先执行：`brew upgrade chromedriver`。\n"
        msg = (
            "未能获取与当前 Chrome 主版本一致的 ChromeDriver（常见于无法访问 Google 下载源）。\n"
            f"{extra}"
            "可选方案：\n"
            "  1) 设置环境变量指向已下载的驱动：`export CHROMEDRIVER_PATH=/path/to/chromedriver`；\n"
            "  2) 删除 Selenium 旧缓存后重试：`rm -rf ~/.cache/selenium`；\n"
            f"原始错误：{exc}"
        )
        raise RuntimeError(msg) from exc


def _parse_media_clock_to_seconds(text: str) -> int | None:
    """
    将播放器上的时间文案转为秒数。
    支持「分:秒」如 4:17；支持「时:分:秒」如 1:02:03。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"[^\d:]+", "", raw)
    parts = [p for p in raw.split(":") if p != ""]
    try:
        if len(parts) == 2:
            a, b = int(parts[0]), int(parts[1])
            return a * 60 + b
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except ValueError:
        pass
    return None


def _time_label_text(el) -> str:
    """部分播放器 .text 为空，用 textContent 兜底。"""
    t = (el.text or "").strip()
    if t:
        return t
    return (el.get_attribute("textContent") or "").strip()


def _click_optional_ack_if_present(driver: webdriver.Chrome) -> None:
    """若 PRD 指定元素存在且可见则点击，否则静默跳过；最后回到 default_content。"""
    driver.switch_to.default_content()
    if not _try_switch_to_context_having(driver, By.XPATH, XPATH_OPTIONAL_ACK):
        return
    try:
        el = driver.find_element(By.XPATH, XPATH_OPTIONAL_ACK)
        if el.is_displayed() and el.is_enabled():
            _native_click(driver, el)
            time.sleep(0.35)
    except (
        StaleElementReferenceException,
        ElementClickInterceptedException,
        NoSuchWindowException,
        NoSuchElementException,
    ):
        pass
    finally:
        driver.switch_to.default_content()


def _section_playback_finished(driver: webdriver.Chrome) -> bool:
    """当前观看时长已达到（或超过）总时长则视为本节播完。"""
    try:
        cur_el = driver.find_element(By.XPATH, XPATH_CURRENT_TIME)
        tot_el = driver.find_element(By.XPATH, XPATH_TOTAL_TIME)
        cur = _parse_media_clock_to_seconds(_time_label_text(cur_el))
        tot = _parse_media_clock_to_seconds(_time_label_text(tot_el))
        if cur is None or tot is None:
            return False
        if tot <= 0:
            return False
        # 允许约 1 秒误差，避免 UI 四舍五入导致永远差 1 秒
        return cur >= tot - 1
    except (NoSuchElementException, StaleElementReferenceException):
        return False


def _click_play(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    last: Exception | None = None
    for _ in range(4):
        try:
            if not _try_switch_to_context_having(driver, By.XPATH, XPATH_PLAY):
                raise TimeoutException("未找到播放按钮（已搜索默认页与各层 iframe）")
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, XPATH_PLAY)))
            _native_click(driver, btn)
            return
        except StaleElementReferenceException as exc:
            last = exc
            time.sleep(0.25)
    if last:
        raise last


def _click_next(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    last: Exception | None = None
    for _ in range(4):
        try:
            driver.switch_to.default_content()
            if not _try_switch_to_context_having(driver, By.XPATH, XPATH_NEXT):
                raise TimeoutException("未找到「下一节」控件（已搜索默认页与各层 iframe）")
            nxt = wait.until(EC.element_to_be_clickable((By.XPATH, XPATH_NEXT)))
            _native_click(driver, nxt)
            return
        except StaleElementReferenceException as exc:
            last = exc
            time.sleep(0.25)
    if last:
        raise last


def _wait_section_done(driver: webdriver.Chrome, _wait: WebDriverWait) -> None:
    deadline = time.monotonic() + MAX_SECTION_SECONDS
    while time.monotonic() < deadline:
        try:
            _click_optional_ack_if_present(driver)
            if not driver.find_elements(By.XPATH, XPATH_CURRENT_TIME):
                _try_switch_to_context_having(driver, By.XPATH, XPATH_CURRENT_TIME)
            if _section_playback_finished(driver):
                return
        except (NoSuchElementException, StaleElementReferenceException, NoSuchWindowException):
            driver.switch_to.default_content()
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(
        f"本节在 {MAX_SECTION_SECONDS} 秒内未检测到播放完成，请核对 PRD 中「当前观看时长 / 总时长」XPath 与网络。"
    )


def main() -> None:
    opts = Options()
    # 需要人工登录，勿用无头模式
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # 启用浏览器静音，避免播放视频时外放声音
    opts.add_argument("--mute-audio")

    try:
        driver = webdriver.Chrome(service=_build_chrome_service(), options=opts)
    except SessionNotCreatedException as e:
        print(
            "启动 Chrome 失败：Chrome 与 ChromeDriver 主版本不一致或驱动无效。\n"
            "可尝试：`brew upgrade chromedriver`，或设置 `CHROMEDRIVER_PATH`，或 `rm -rf ~/.cache/selenium` 后重试。",
            file=sys.stderr,
        )
        raise
    wait = WebDriverWait(driver, 30)

    try:
        driver.maximize_window()
        driver.get(COURSE_URL)

        print("请在浏览器中完成登录，并打开到需要自动连播的视频页。")
        print("确认当前活动标签页就是要控制的页面后，回到终端按回车开始循环…")
        input()

        _prepare_target_tab(driver)

        section = 0
        while True:
            section += 1
            _click_optional_ack_if_present(driver)
            print(f"[{section}] 点击播放…")
            try:
                _click_play(driver, wait)
            except TimeoutException:
                print("未找到播放按钮，请确认已在视频页且 XPath 仍有效。", file=sys.stderr)
                raise

            print(f"[{section}] 等待本节播完…")
            _wait_section_done(driver, wait)

            print(f"[{section}] 点击下一节…")
            _click_next(driver, wait)
            _click_optional_ack_if_present(driver)
            time.sleep(2)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
