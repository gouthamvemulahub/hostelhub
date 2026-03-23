from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import StudentProfile, Room, RoomAllotment, Complaint, Notice, StaffMember, HostelBlock


class StudentRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        """Ensure email is unique — no two students with same email."""
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email address is already registered.')
        return email


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        exclude = ['user', 'created_at']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'course': forms.TextInput(attrs={
                'style': 'text-transform:uppercase;',
                'oninput': 'this.value=this.value.toUpperCase()',
                'placeholder': 'e.g. B.TECH, MBA, MCA',
                'autocomplete': 'off',
            }),
            'phone': forms.TextInput(attrs={
                'type': 'tel',
                'maxlength': '10',
                'minlength': '10',
                'pattern': '[0-9]{10}',
                'placeholder': 'Enter 10-digit mobile number',
                'oninput': 'this.value=this.value.replace(/[^0-9]/g,"").slice(0,10)',
                'title': 'Please enter exactly 10 digits',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['guardian_name'].required  = False
        self.fields['guardian_phone'].required = False
        self.fields['profile_photo'].required  = False
        self.fields['block'].required          = False
        self.fields['block'].empty_label       = '-- Select Block (Optional) --'
        self.fields['block'].queryset          = HostelBlock.objects.filter(is_active=True)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_course(self):
        """Always save course in uppercase regardless of what was typed."""
        course = self.cleaned_data.get('course', '')
        return course.upper() if course else course

    def clean_phone(self):
        """Phone number must be exactly 10 digits."""
        phone = self.cleaned_data.get('phone', '').strip()
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) != 10:
            raise forms.ValidationError('Phone number must be exactly 10 digits.')
        return digits

    def clean_year_of_study(self):
        """Year of study must be between 1 and 6."""
        year = self.cleaned_data.get('year_of_study')
        if year is not None and (year < 1 or year > 6):
            raise forms.ValidationError('Year of study must be between 1 and 6.')
        return year


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['block'].required    = False
        self.fields['block'].empty_label = '-- Select Block --'
        self.fields['block'].queryset    = HostelBlock.objects.filter(is_active=True)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class RoomAllotmentForm(forms.ModelForm):
    class Meta:
        model = RoomAllotment
        fields = ['student', 'room', 'remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional remarks...'}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        warden_block = kwargs.pop('warden_block', None)
        super().__init__(*args, **kwargs)

        # Filter rooms by warden block
        if warden_block:
            self.fields['room'].queryset = Room.objects.filter(
                status='available', block=warden_block)
        elif student and student.block:
            self.fields['room'].queryset = Room.objects.filter(
                status='available', block=student.block)
        else:
            self.fields['room'].queryset = Room.objects.filter(status='available')

        self.fields['remarks'].required = False

        # Show room info next to student name
        students_with_rooms = {}
        from .models import RoomAllotment
        active_allotments = RoomAllotment.objects.filter(
            is_active=True
        ).select_related('student', 'room')
        for a in active_allotments:
            students_with_rooms[a.student.id] = a.room.room_number

        # Filter students by warden block
        from .models import StudentProfile
        if warden_block:
            all_students = StudentProfile.objects.select_related('user').filter(block=warden_block)
        else:
            all_students = StudentProfile.objects.select_related('user').all()

        choices = [('', '---------')]
        for s in all_students:
            room_info = f' → Room {students_with_rooms[s.id]}' if s.id in students_with_rooms else ' → No Room'
            label = f'{s.user.get_full_name()} ({s.roll_number}){room_info}'
            choices.append((s.id, label))
        self.fields['student'].choices = choices

        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            
    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        room = cleaned_data.get('room')
        if student and RoomAllotment.objects.filter(student=student, is_active=True).exists():
            raise forms.ValidationError("This student already has an active room allotment.")
        if room and room.available_beds <= 0:
            raise forms.ValidationError("This room is full.")
        return cleaned_data


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ['category', 'priority', 'title', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class ComplaintUpdateForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ['status', 'admin_remarks']
        widgets = {
            'admin_remarks': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'content', 'priority', 'photo', 'is_active']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class StaffMemberForm(forms.ModelForm):
    class Meta:
        model = StaffMember
        fields = ['name', 'role', 'phone', 'email', 'address', 'shift', 'photo', 'status', 'joined_date', 'notes']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'notes':   forms.Textarea(attrs={'rows': 2}),
            'joined_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-control'