import os
import subprocess
import sys

def main():
    # 1. 設定路徑
    alphas_dir = "alphas"
    # [修正] 指定 brain.py 的正確位置 (在 alphas 資料夾內)
    brain_script = os.path.join(alphas_dir, "brain.py")
    
    # 檢查資料夾
    if not os.path.exists(alphas_dir):
        print(f"錯誤：找不到 '{alphas_dir}' 資料夾。")
        return

    # 檢查 brain.py 是否真的在 alphas 裡
    if not os.path.exists(brain_script):
        print(f"錯誤：找不到 '{brain_script}'。請確認 brain.py 確實位於 alphas 資料夾內。")
        return

    # 2. 掃描策略檔 (.py)，排除 __init__.py 和 brain.py 本身
    files = [f for f in os.listdir(alphas_dir) 
             if f.endswith(".py") 
             and f != "__init__.py" 
             and f != "brain.py"] # 排除 brain.py 避免選到它
    
    if not files:
        print(f"警告：在 '{alphas_dir}' 中找不到任何策略檔案。")
        return

    # 3. 顯示互動選單
    print("\n" + "="*30)
    print("   QUANT BRAIN 策略啟動器")
    print("="*30)
    
    for i, f in enumerate(files):
        print(f"[{i+1}] {f}")
    
    print("-" * 30)

    # 4. 讓使用者選擇
    selected_file = None
    while True:
        try:
            user_input = input("請輸入策略編號 (或是按 q 離開): ").strip()
            
            if user_input.lower() == 'q':
                print("已離開。")
                return

            idx = int(user_input) - 1
            if 0 <= idx < len(files):
                selected_file = files[idx]
                break
            else:
                print("編號無效，請重新輸入。")
        except ValueError:
            print("請輸入有效的數字。")

    # 5. 組裝指令並執行
    # 這裡的邏輯變成了: python alphas/brain.py alphas/strategy_name.py
    strategy_path = os.path.join(alphas_dir, selected_file)
    print(f"\n>> 正在啟動策略回測: {selected_file} ...\n")
    
    try:
        # [修正] 這裡的第一個參數改為 brain_script (即 alphas/brain.py)
        subprocess.run([sys.executable, brain_script, strategy_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[Error] 執行過程中發生錯誤 (Exit Code: {e.returncode})")
    except KeyboardInterrupt:
        print("\n使用者中斷執行。")

if __name__ == "__main__":
    main()