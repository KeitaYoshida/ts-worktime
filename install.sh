#!/bin/bash

# スクリプトを実行するディレクトリに移動
cd "$(dirname "$0")"

# 必要なパッケージのインストール
echo "必要なパッケージをインストールします..."
sudo apt-get update
sudo apt-get install -y \
    python3-pyscard \
    python3-requests \
    python3-tk \
    python3-sdnotify \
    sox  # ビープ音用

# ログディレクトリの作成
mkdir -p logs
chmod 755 logs

# サービスファイルをsystemdディレクトリにコピー
sudo cp worktime.service /etc/systemd/system/

# サービスファイルの権限設定
sudo chmod 644 /etc/systemd/system/worktime.service

# systemdの設定を再読み込み
sudo systemctl daemon-reload

# サービスを有効化
sudo systemctl enable worktime.service

# サービスを開始
sudo systemctl start worktime.service

# 状態を確認
sudo systemctl status worktime.service

echo "インストールが完了しました。"
echo "以下のコマンドでサービスを制御できます："
echo "  開始: sudo systemctl start worktime"
echo "  停止: sudo systemctl stop worktime"
echo "  再起動: sudo systemctl restart worktime"
echo "  状態確認: sudo systemctl status worktime"
echo "  ログ確認: sudo journalctl -u worktime -f" 