from django.db import migrations


def add_default_rules(apps, schema_editor):
    HostelRule = apps.get_model('hostelapp', 'HostelRule')

    rules = [
        # Room Rules
        ('room', 'Keep your room clean', 'Students must keep their rooms clean and tidy at all times. Rooms will be inspected weekly by the warden.', 1),
        ('room', 'No damage to property', 'Students are responsible for any damage caused to hostel property in their room. Repair costs will be charged.', 2),
        ('room', 'No cooking in rooms', 'Cooking inside rooms is strictly prohibited. Use the mess facility only.', 3),
        ('room', 'Lights out by 11 PM', 'All lights and electronic devices must be switched off by 11:00 PM on weekdays.', 4),

        # Visitor Rules
        ('visitor', 'Visitors allowed only in common area', 'Visitors are not permitted inside student rooms under any circumstances.', 1),
        ('visitor', 'Visiting hours: 9 AM to 6 PM', 'Visitors are allowed only between 9:00 AM and 6:00 PM on weekdays and weekends.', 2),
        ('visitor', 'Register visitors at gate', 'All visitors must register their name and ID at the security gate before entry.', 3),

        # Fee Rules
        ('fee', 'Fee due on joining date every month', 'Monthly hostel fee must be paid on or before the date of joining every month.', 1),
        ('fee', 'Late fee penalty', 'A late fee of Rs. 50 per day will be charged for payments made after the due date.', 2),
        ('fee', 'No fee refund after 7 days', 'Fee once paid will not be refunded after 7 days of the payment date.', 3),

        # Disciplinary Rules
        ('disciplinary', 'No ragging', 'Ragging in any form is strictly prohibited and will result in immediate expulsion from the hostel.', 1),
        ('disciplinary', 'No alcohol or smoking', 'Consumption of alcohol, tobacco or any drugs inside hostel premises is strictly banned.', 2),
        ('disciplinary', 'No loud music or noise', 'Playing loud music or creating disturbance after 9 PM is not allowed.', 3),
        ('disciplinary', 'Respect all residents and staff', 'Students must treat all fellow residents and hostel staff with respect at all times.', 4),

        # Gate Timing Rules
        ('gate', 'Gate closes at 10 PM', 'The main gate will be locked at 10:00 PM every day. Students must return before closing time.', 1),
        ('gate', 'Late entry requires permission', 'Students returning after 10 PM must get prior written permission from the warden.', 2),
        ('gate', 'Sign in/out at gate', 'All students must sign the gate register whenever they leave or return to the hostel.', 3),

        # WiFi Rules
        ('wifi', 'WiFi for academic use only', 'Hostel WiFi must be used only for academic purposes. Streaming, gaming and downloading is prohibited.', 1),
        ('wifi', 'No sharing of WiFi credentials', 'Students must not share their WiFi login credentials with anyone including visitors.', 2),
        ('wifi', 'WiFi timings: 6 AM to 11 PM', 'WiFi access is available from 6:00 AM to 11:00 PM only.', 3),

        # Holiday/Leave Rules
        ('leave', 'Inform warden before leave', 'Students must inform the warden at least 1 day before going on leave.', 1),
        ('leave', 'Maximum 7 days casual leave', 'Students are allowed a maximum of 7 days casual leave per semester.', 2),
        ('leave', 'Parents must approve long leave', 'For leave exceeding 3 days, written consent from parents is mandatory.', 3),

        # Emergency Rules
        ('emergency', 'Emergency contact: Warden', 'In case of any emergency, immediately contact the warden at the provided number.', 1),
        ('emergency', 'Know fire exit locations', 'All students must be aware of fire exit locations in the hostel building.', 2),
        ('emergency', 'Do not use lifts during fire', 'In case of fire, never use the elevator. Use staircases only.', 3),
        ('emergency', 'Report medical emergencies immediately', 'Any medical emergency must be reported to the warden immediately for assistance.', 4),
    ]

    for category, title, description, order in rules:
        HostelRule.objects.get_or_create(
            category=category,
            title=title,
            defaults={'description': description, 'order': order, 'is_active': True}
        )


def remove_default_rules(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hostelapp', '0010_hostelrule'),
    ]

    operations = [
        migrations.RunPython(add_default_rules, remove_default_rules),
    ]