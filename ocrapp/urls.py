from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),  # Landing page route
    path('user-admin/', views.user_admin, name='user_admin'),  # User/Admin selection route
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('upload/', views.upload_image, name='upload_image'),
    path('generate_pass/', views.generate_pass, name='generate_pass'),
    path('download_pass/', views.download_pass, name='download_pass'),
    path('details/', views.details_page, name='details_page'),
]
