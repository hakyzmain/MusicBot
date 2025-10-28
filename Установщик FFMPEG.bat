@echo off
color 08
chcp 65001 <nul
echo Установка FFmpeg...
mkdir C:\ffmpeg 2>nul
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile '%TEMP%\ffmpeg.zip'"
powershell -Command "Expand-Archive -Path '%TEMP%\ffmpeg.zip' -DestinationPath '%TEMP%\ffmpeg_temp' -Force"
xcopy "%TEMP%\ffmpeg_temp\ffmpeg-master-latest-win64-gpl\*" "C:\ffmpeg" /E /I /Y
setx PATH "%PATH%;C:\ffmpeg\bin"
echo Успех
pause