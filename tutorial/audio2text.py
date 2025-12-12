from google import genai

client = genai.Client(api_key="")
myfile = client.files.upload(file='./test.mp3')
prompt = '產生音訊資料的轉錄稿'

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[prompt, myfile]
)

print(response.text)