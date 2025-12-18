# 1. 파이썬 3.9 버전을 기반으로 합니다.
FROM python:3.9

# 2. 작업 폴더를 설정합니다.
WORKDIR /app

# 3. 필요한 라이브러리 목록을 복사하고 설치합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 현재 폴더의 모든 코드를 컨테이너 안으로 복사합니다.
COPY . .

# 5. 서버를 실행합니다. (0.0.0.0은 외부 접속 허용)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]