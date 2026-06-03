@echo off
chcp 65001 > nul
title GitHubにアップロード中...

echo ==========================================
echo   GitHub へアップロードしています...
echo ==========================================
echo.

cd /d "%~dp0"

git add index.html vercel.json
git commit -m "update"
git push origin main

if errorlevel 1 (
  echo.
  echo [エラー] アップロードに失敗しました。
  echo GitHubにログインしているか確認してください。
) else (
  echo.
  echo [完了] GitHubへのアップロードが完了しました！
  echo Vercel が自動でデプロイを開始します。
)

echo.
pause
