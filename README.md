# bestSleeping

住んでいる地域の外気温と、就寝時の環境データをもとに、エアコンの推奨設定温度を提案するシステムです。

## リポジトリ

このリポジトリは、bestSleeping のAPIサーバー用リポジトリです。

M5Stack側のリポジトリはこちら：  
https://github.com/uyuuuuu/BestSleeping_m5stack

## 概要

bestSleeping は、就寝時の環境データと過去のエアコン設定履歴をもとに、その日の推奨エアコン設定温度を提案するシステムです。

M5Stack Core2で室温・照度を取得し、部屋が暗くなったタイミングを就寝開始の目安として検知します。その後、GASに記録された過去データをAPIサーバーが取得し、機械学習によって推奨設定温度を算出します。

算出された推奨温度は、M5Stack Core2の画面とLINEに通知されます。

## 主な機能

- M5Stack Core2による室温・照度の取得
- 照度センサーによる就寝タイミングの検知
- GASへの環境データ・設定温度の記録
- 外気温と睡眠開始時刻に基づくエアコン設定温度の推定
- LINEへの推奨温度通知
- 室温と外気温の関係を可視化するグラフ表示

## 使用技術

### APIサーバー

- Python
- Flask
- pandas
- scikit-learn
- matplotlib
- LINE Messaging API
- OpenWeather API

### デバイス側

- M5Stack Core2
- PlatformIO
- Arduino / C++
- ENV III Unit
- DLight Unit

### データ管理

- Google Apps Script
- Google Spreadsheet

## システム構成
<img width="1920" height="1080" alt="システム構成図" src="https://github.com/user-attachments/assets/ba635492-6bbb-4cbc-bf4d-f3c321f16e1c" />
