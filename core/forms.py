from django import forms


MAX_PASSWORD_BYTES = 72


class RegisterForm(forms.Form):
    username = forms.CharField(label="Имя пользователя", max_length=50)
    email = forms.EmailField(label="Email")
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput, min_length=6, max_length=MAX_PASSWORD_BYTES)
    password2 = forms.CharField(
        label="Подтверждение пароля", widget=forms.PasswordInput, min_length=6, max_length=MAX_PASSWORD_BYTES
    )

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли должны совпадать.")
        if password1 and len(password1.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise forms.ValidationError("Пароль не должен превышать 72 байта.")
        return cleaned


class LoginForm(forms.Form):
    username = forms.CharField(label="Имя пользователя")
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)


class BookForm(forms.Form):
    title = forms.CharField(label="Название", max_length=200)
    author = forms.CharField(label="Автор", max_length=200)
    isbn = forms.CharField(label="ISBN", max_length=20)
    total_copies = forms.IntegerField(label="Всего копий", min_value=1)
    available_copies = forms.IntegerField(label="Доступные копии", min_value=0)

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get("total_copies") or 0
        available = cleaned.get("available_copies") or 0
        if available > total:
            raise forms.ValidationError("Доступные копии не могут превышать общее количество.")
        return cleaned