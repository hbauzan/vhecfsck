#!/usr/bin/env bash
# Contributor console for vhecfsck.
# Product surface is the CLI (`uvx vhecfsck`). This panel is for a git checkout.
# macOS only until the Linux port (P9-09). See roadmap/next-ticket.md.
# Not a daemon supervisor: no background services, no pid files, no log dir.

set -o pipefail

ESC_SEQ="\033["
C_RESET="${ESC_SEQ}0m"
C_BOLD="${ESC_SEQ}1m"
C_DIM="${ESC_SEQ}2m"
C_BLUE="${ESC_SEQ}1;34m"
C_CYAN="${ESC_SEQ}1;36m"
C_GREEN="${ESC_SEQ}1;32m"
C_YELLOW="${ESC_SEQ}1;33m"
C_RED="${ESC_SEQ}1;31m"
C_PURPLE="${ESC_SEQ}1;35m"
C_WHITE="${ESC_SEQ}1;37m"

BANNER="DON'T PANIC — Vector Index"
LABEL_BOOTSTRAP="Infinite Improbability Drive"
LABEL_VERIFY="The mice would like a word"
LABEL_DEMO="Forty-two"
LABEL_SERVE="Heart of Gold"
LABEL_CLEAN="Point-of-View Gun"
LABEL_DUMP="Total Perspective Vortex"
LABEL_EXIT="So long, and thanks for all the fish"
LABEL_INVALID="I think you ought to know I'm feeling very depressed."
THURSDAY="This must be Thursday. I never could get the hang of Thursdays."
MOSTLY_HARMLESS="Mostly harmless"

EXIT_OK=0
EXIT_FAIL=2
EXIT_INCONCLUSIVE=3
EXIT_USAGE=4

log_info() { printf "${C_CYAN}[INFO]${C_RESET} %s\n" "$1"; }
log_ok()   { printf "${C_GREEN}[ OK ]${C_RESET} %s\n" "$1"; }
log_warn() { printf "${C_YELLOW}[WARN]${C_RESET} %s\n" "$1"; }
log_fail() { printf "${C_RED}[FAIL]${C_RESET} %s\n" "$1" >&2; }

show_progress_bar() {
    local percent="$1"
    local title="$2"
    local quote="${3:-"Don't Panic"}"
    local width=20
    local filled=$(( percent * width / 100 ))
    local empty=$(( width - filled ))
    local bar=""
    local i
    for ((i=0; i<filled; i++)); do bar="${bar}█"; done
    for ((i=0; i<empty; i++)); do bar="${bar}░"; done
    printf "${C_PURPLE}[BUSY]${C_RESET} %s [${C_GREEN}%s${C_RESET}] %3d%%  ${C_DIM}(%s)${C_RESET}\r" \
        "${title}" "${bar}" "${percent}" "${quote}"
    if [ "${percent}" -ge 100 ]; then
        printf "\n"
    fi
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

detected_uname() {
    if [ -n "${SETUP_SH_UNAME:-}" ]; then
        printf '%s\n' "${SETUP_SH_UNAME}"
        return 0
    fi
    uname -s
}

require_macos() {
    case "$(detected_uname)" in
        Darwin)
            return 0
            ;;
        *)
            log_fail "${THURSDAY} This console is macOS-only until the publish-readiness Linux port (P9-09)."
            return 1
            ;;
    esac
}

print_banner() {
    printf "${C_BLUE}╔══════════════════════════════════════════════════════════════════╗${C_RESET}\n"
    printf "${C_BLUE}║  ${C_WHITE}${C_BOLD}%-64s${C_RESET}${C_BLUE}║${C_RESET}\n" "${BANNER}"
    printf "${C_BLUE}║  ${C_CYAN}%-64s${C_RESET}${C_BLUE}║${C_RESET}\n" "vhecfsck contributor console — no daemon, no SaaS"
    printf "${C_BLUE}╚══════════════════════════════════════════════════════════════════╝${C_RESET}\n"
}

print_options() {
    printf "${C_BOLD}${C_WHITE}OPTIONS:${C_RESET}\n"
    printf "  ${C_CYAN}[1]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "detect uv, then uv sync — base install + dev group, never all extras" "${LABEL_BOOTSTRAP}"
    printf "  ${C_CYAN}[2]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "make verify — run strict quality gate (lint, mypy, pytest, coverage)" "${LABEL_VERIFY}"
    printf "  ${C_CYAN}[3]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "uv run vhecfsck demo — 60s synthetic index audit demo (pgvector #244)" "${LABEL_DEMO}"
    printf "  ${C_CYAN}[4]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "uv run vhecfsck serve — launch 3D visualizer web server on :8765" "${LABEL_SERVE}"
    printf "  ${C_CYAN}[5]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "kill orphaned pytest processes for this checkout" "${LABEL_CLEAN}"
    printf "  ${C_CYAN}[6]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "dump codebase context to vhecfsck.txt for AI agents" "${LABEL_DUMP}"
    printf "  ${C_WHITE}[0]${C_RESET} ${C_BOLD}${C_WHITE}%s${C_RESET}  ${C_DIM}(%s)${C_RESET}\n" \
        "Exit the panel" "${LABEL_EXIT}"
}

print_help() {
    print_banner
    printf "\n"
    print_options
    printf "\n${C_DIM}Non-interactive verbs: help | sync | verify | demo | serve | clean | dump${C_RESET}\n"
    printf "${C_DIM}The product is the CLI. This panel does not supervise processes.${C_RESET}\n"
}

refresh_path() {
    # Only add well-known locations when uv is still missing. Never shadow an
    # explicit PATH (tests inject a fake uv; a contributor may pin a version).
    if command_exists uv; then
        return 0
    fi
    export PATH="${PATH}:${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin"
    if [ -f "${HOME}/.local/bin/env" ]; then
        # shellcheck disable=SC1091
        . "${HOME}/.local/bin/env"
    fi
}

ensure_uv() {
    if command_exists uv; then
        log_ok "uv $(uv --version 2>/dev/null) — ${MOSTLY_HARMLESS}"
        return 0
    fi
    refresh_path
    if command_exists uv; then
        log_ok "uv $(uv --version 2>/dev/null) — ${MOSTLY_HARMLESS}"
        return 0
    fi

    log_warn "uv not found."
    if [ "${SETUP_SH_SKIP_PREREQ_PROMPT:-}" = "1" ] || [ ! -t 0 ]; then
        log_fail "Install uv from https://docs.astral.sh/uv/ then re-run."
        return "${EXIT_INCONCLUSIVE}"
    fi

    printf "${C_YELLOW}Install uv with the official installer? [y/N]: ${C_RESET}"
    read -r resp
    case "${resp}" in
        y|Y)
            curl -LsSf https://astral.sh/uv/install.sh | sh
            refresh_path
            if command_exists uv; then
                log_ok "uv installed — ${MOSTLY_HARMLESS}"
                return 0
            fi
            log_fail "uv installer finished but uv is not on PATH."
            return "${EXIT_FAIL}"
            ;;
        *)
            log_fail "Install uv from https://docs.astral.sh/uv/ then re-run."
            return "${EXIT_INCONCLUSIVE}"
            ;;
    esac
}

ensure_env_synced() {
    ensure_uv || return $?
    if [ ! -f pyproject.toml ]; then
        return 0
    fi
    if [ ! -d ".venv" ] || ! uv run python -c "import vhecfsck, pyarrow" >/dev/null 2>&1; then
        log_warn "Virtual environment missing or out of sync. Synchronising..."
        cmd_sync || return $?
    fi
    return 0
}

cmd_sync() {
    ensure_uv || return $?
    log_info "${LABEL_BOOTSTRAP}: uv sync --group dev --extra lancedb"
    if [ -t 1 ]; then
        show_progress_bar 10 "Synchronising development environment..." "${LABEL_BOOTSTRAP}"
    fi
    if uv sync --group dev --extra lancedb; then
        if [ -t 1 ]; then
            show_progress_bar 100 "Environment synchronised" "${LABEL_BOOTSTRAP}"
        fi
        log_ok "Environment synchronised — ${MOSTLY_HARMLESS}"
        return "${EXIT_OK}"
    fi
    log_fail "uv sync failed."
    return "${EXIT_FAIL}"
}

cmd_verify() {
    ensure_uv || return $?
    if [ ! -f Makefile ]; then
        log_warn "${THURSDAY} ${LABEL_VERIFY}: make verify is not in this checkout yet (P0-04)."
        return "${EXIT_INCONCLUSIVE}"
    fi
    ensure_env_synced || return $?
    log_info "${LABEL_VERIFY}: make verify"
    if make verify; then
        log_ok "Gate green — ${MOSTLY_HARMLESS}"
        return "${EXIT_OK}"
    fi
    log_fail "make verify failed."
    return "${EXIT_FAIL}"
}

vhecfsck_has_command() {
    local name="$1"
    local out
    if ! command_exists uv; then
        return 1
    fi
    out="$(uv run vhecfsck "${name}" --help 2>&1)" || true
    if printf '%s' "${out}" | grep -q "No such command"; then
        return 1
    fi
    return 0
}

cmd_demo() {
    ensure_uv || return $?
    ensure_env_synced || return $?
    if ! vhecfsck_has_command demo; then
        log_warn "${THURSDAY} ${LABEL_DEMO}: vhecfsck demo is not built yet (P3-05)."
        return "${EXIT_INCONCLUSIVE}"
    fi
    log_info "${LABEL_DEMO}: uv run vhecfsck demo"
    uv run vhecfsck demo
    return $?
}

cmd_serve() {
    ensure_uv || return $?
    ensure_env_synced || return $?
    if ! vhecfsck_has_command serve; then
        log_warn "${THURSDAY} ${LABEL_SERVE}: vhecfsck serve is not built yet (P4-06)."
        return "${EXIT_INCONCLUSIVE}"
    fi
    log_info "${LABEL_SERVE}: uv run vhecfsck serve (foreground; Ctrl+C stops it)"
    log_info "Server URL: http://127.0.0.1:8765"
    uv run vhecfsck serve
    return $?
}

cmd_clean() {
    log_info "${LABEL_CLEAN}: searching for orphaned processes in this checkout"
    if [ "${SETUP_SH_IN_TEST:-}" = "1" ]; then
        log_ok "Running inside test harness — skipping process cleanup — ${MOSTLY_HARMLESS}"
        return "${EXIT_OK}"
    fi
    local root
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    python3 "${root}/scripts/clean_orphans.py"
    return $?
}

cmd_dump() {
    log_info "${LABEL_DUMP}: generating codebase context dump (vhecfsck.txt)"
    local root
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    python3 "${root}/scripts/dump_context.py" "${PWD}"
    return $?
}

pause_if_tty() {
    if [ -t 0 ]; then
        printf "\n${C_DIM}Press Enter to return to the panel.${C_RESET}"
        read -r _
    fi
}

show_menu() {
    while true; do
        if [ -t 1 ]; then
            clear
        fi
        print_banner
        printf "\n"
        print_options
        printf "\n${C_BOLD}Select [0-6]: ${C_RESET}"
        read -r option || exit "${EXIT_OK}"
        case "${option}" in
            1)
                cmd_sync
                pause_if_tty
                ;;
            2)
                cmd_verify
                pause_if_tty
                ;;
            3)
                cmd_demo
                pause_if_tty
                ;;
            4)
                cmd_serve
                pause_if_tty
                ;;
            5)
                cmd_clean
                pause_if_tty
                ;;
            6)
                cmd_dump
                pause_if_tty
                ;;
            0)
                printf "\n${C_CYAN}%s${C_RESET}\n" "${LABEL_EXIT}"
                exit "${EXIT_OK}"
                ;;
            *)
                printf "\n${C_RED}%s${C_RESET}\n" "${LABEL_INVALID}"
                ;;
        esac
    done
}

if ! require_macos; then
    exit "${EXIT_INCONCLUSIVE}"
fi

case "${1:-}" in
    "")
        show_menu
        ;;
    help|-h|--help)
        print_help
        exit "${EXIT_OK}"
        ;;
    sync)
        cmd_sync
        exit $?
        ;;
    verify)
        cmd_verify
        exit $?
        ;;
    demo)
        cmd_demo
        exit $?
        ;;
    serve)
        cmd_serve
        exit $?
        ;;
    clean|kill)
        cmd_clean
        exit $?
        ;;
    dump|context|dump-context)
        cmd_dump
        exit $?
        ;;
    *)
        printf '%s\n' "${LABEL_INVALID}" >&2
        printf 'Usage: ./setup.sh [help|sync|verify|demo|serve|clean|dump]\n' >&2
        exit "${EXIT_USAGE}"
        ;;
esac
