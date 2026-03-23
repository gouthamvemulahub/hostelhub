from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hostelapp', '0016_merge_20260316_0323'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(choices=[('aadhar','Aadhar Card'),('pan','PAN Card'),('college_id','College ID Card'),('tc','Transfer Certificate'),('marksheet','Marksheet'),('passport','Passport'),('voter_id','Voter ID'),('other','Other')], max_length=20)),
                ('title', models.CharField(max_length=200)),
                ('file', models.FileField(upload_to='student_documents/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('is_verified', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='hostelapp.studentprofile')),
                ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_documents', to='auth.user')),
            ],
            options={'ordering': ['-uploaded_at']},
        ),
    ]