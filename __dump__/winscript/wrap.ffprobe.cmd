@echo off
setlocal
set ffprobe=ffprobe -v error

call :%*
goto :eof

:w
:width
%ffprobe% -select_streams v:0 -show_entries stream=width -of csv=p=0 -i %*
goto :eof

:h
:height
%ffprobe% -select_streams v:0 -show_entries stream=height -of csv=p=0 -i %*
goto :eof

:res
:resolution
%ffprobe% -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=* -i %*
goto :eof

:v.encoder
:v.codecname
%ffprobe% -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 -i %*
goto :eof

:all.json
%ffprobe% -show_streams -of json -i %*
goto :eof

:v.prof
:v.profile
%ffprobe% -select_streams v:0 -show_entries stream=profile -of csv=p=0 -i %*
goto :eof

:pixfmt
%ffprobe% -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 -i %*
goto :eof
