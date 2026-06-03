@echo off
chcp 65001 > nul
title 無限文字起こし

echo ==========================================
echo   無限文字起こし セットアップ・起動
echo ==========================================
echo.

:: Python チェック
python --version > nul 2>&1
if errorlevel 1 (
    echo [エラー] Python が見つかりません。
    echo.
    echo 以下の手順でインストールしてください：
    echo 1. https://www.python.org/downloads/ を開く
    echo 2. "Download Python 3.x.x" ボタンをクリック
    echo 3. インストーラーを実行（"Add Python to PATH" に必ずチェック！）
    echo 4. このファイルをもう一度実行
    echo.
    pause
    exit /b 1
)

echo [OK] Python が見つかりました
echo.

:: パッケージインストール
echo 必要なパッケージをインストール中...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [エラー] パッケージのインストールに失敗しました
    pause
    exit /b 1
)
echo [OK] パッケージのインストール完了
echo.

:: アプリ起動
echo アプリを起動します。ブラウザが自動で開きます...
echo 終了するには このウィンドウを閉じるか Ctrl+C を押してください。
echo.
python app.py
pause
