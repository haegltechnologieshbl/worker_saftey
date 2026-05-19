from django import forms
from django.contrib.auth import get_user_model
from .models import Video

User = get_user_model()


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ['title', 'video_file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter video title'}),
            'video_file': forms.FileInput(attrs={'class': 'form-control'})
        }

    def clean_video_file(self):
        video = self.cleaned_data.get('video_file')
        if video:
            ext = video.name.split('.')[-1].lower()
            if ext not in ['mp4', 'avi', 'mov']:
                raise forms.ValidationError('Unsupported video format. Please use MP4, AVI, or MOV.')
        return video


class EmployeeCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Initial password'}),
        min_length=6,
        help_text='Give this to the employee. Min 6 characters.'
    )
    enrollment_video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
        help_text='Upload a short video (5-15 seconds) of the employee turning their head left/right/up/down. '
                  'The system will extract face encodings from multiple angles. Optional if photo is provided.'
    )

    class Meta:
        model = User
        fields = ['username', 'employee_id', 'first_name', 'last_name', 'email',
                  'phone_number', 'department', 'photo']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'EMP001'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean_employee_id(self):
        eid = self.cleaned_data.get('employee_id')
        if not eid:
            raise forms.ValidationError('Employee ID is required.')
        return eid

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('photo') and not cleaned.get('enrollment_video'):
            raise forms.ValidationError(
                'Provide a photo OR an enrollment video for face recognition.'
            )
        return cleaned

    def clean_enrollment_video(self):
        v = self.cleaned_data.get('enrollment_video')
        if v:
            ext = v.name.split('.')[-1].lower()
            if ext not in ['mp4', 'avi', 'mov', 'webm']:
                raise forms.ValidationError('Use MP4, AVI, MOV, or WEBM.')
        return v

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'employee'
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class EmployeeEditForm(forms.ModelForm):
    enrollment_video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
        help_text='(Optional) Upload a new enrollment video to replace face encodings.'
    )

    class Meta:
        model = User
        fields = ['employee_id', 'first_name', 'last_name', 'email',
                  'phone_number', 'department', 'photo']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
