from django.http import HttpResponse   
def index(request):
    return HttpResponse("D-Order API 서버가 정상 작동 중입니다 ✅ ")
