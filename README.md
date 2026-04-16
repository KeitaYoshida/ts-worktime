# ts-worktime

Raspberry Pi 向けに作成した勤怠管理アプリです。  
通常運用は Raspberry Pi 前提ですが、開発確認用として Mac でも GUI を起動できるようにしています。

実運用向けのローカルファイルは Git 管理から外しています。

- 実設定: `config.json`
- 設定雛形: `config.example.json`
- ログ: `logs/*.log`
- ローカルDB: `attendance.db`
- 同期済みユーザーデータ: `user_data.json`

## Mac 開発モードについて

Mac では以下の機能は無効になります。

- カードリーダー読取
- GPIO ブザー
- `systemd` 通知

その代わり、以下は確認できます。

- メイン GUI の表示
- 出勤 / 退勤ボタンの動作
- カード登録画面への切り替えと戻る動作
- API 通信を含む通常ロジックの確認

## 前提

- `python.org` 版 Python 3.14 をインストール済み
- インストール後に `Install Certificates.command` も実行済み

`python.org` 版は Homebrew 版 Python と共存できます。  
このプロジェクトでは PATH を変更せず、フルパス指定で利用する想定です。

## 初回セットアップ

プロジェクト直下で実行します。

```bash
cd /Users/tamakawatarou/dev/ts-worktime
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-mac.txt
```

`tkinter` の動作確認をしたい場合:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m tkinter
```

小さな Tk ウィンドウが出れば OK です。

## Mac での起動方法

一番簡単なのは起動スクリプトを使う方法です。

```bash
cd /Users/tamakawatarou/dev/ts-worktime
./run_mac.sh
```

もし過去に Homebrew 版 Python で `.venv` を作っていた場合でも、`run_mac.sh` が自動で検出して作り直します。

## 手動で起動する方法

```bash
cd /Users/tamakawatarou/dev/ts-worktime
source .venv/bin/activate
python main.py
```

## 起動スクリプトの挙動

`run_mac.sh` は以下を自動で行います。

- `python.org` 版 Python の存在確認
- `.venv` が無ければ自動作成
- `pip` 更新
- `requirements-mac.txt` のインストール
- アプリ起動

Mac では Raspberry Pi 専用ライブラリを不要にするため、`requirements.txt` ではなく `requirements-mac.txt` を使います。

## 画面構成

カード登録は別アプリではなく、本体アプリ内の画面切り替えで動作します。

- 通常時: 出退勤画面
- `カード登録` ボタン押下: 登録画面へ切り替え
- `閉じる` ボタン押下: 出退勤画面へ戻る

登録画面の表示中は、カードタッチがあっても打刻処理には流れず、登録処理だけが動作します。

## よくある詰まりどころ

### `No module named '_tkinter'`

`python.org` 版ではない Python を使っている可能性があります。  
`run_mac.sh` を使うか、`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3` を使ってください。

### SSL 証明書のエラー

`python.org` 版インストール後に表示された `Install Certificates.command` を実行してください。

### カードリーダーが使えない

Mac 開発モードでは仕様です。  
実機確認は Raspberry Pi 上で行ってください。
