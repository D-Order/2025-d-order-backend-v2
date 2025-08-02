
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('booth', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Menu',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('menu_name', models.CharField(max_length=100)),
                ('menu_description', models.TextField(blank=True)),
                ('menu_category', models.CharField(choices=[('메뉴', '메뉴'), ('음료', '음료')], max_length=10)),
                ('menu_price', models.FloatField()),
                ('menu_amount', models.PositiveIntegerField()),
                ('menu_image', models.ImageField(blank=True, null=True, upload_to='menu_images/')),
                ('booth', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='booth.booth')),
            ],
        ),
        migrations.CreateModel(
            name='SetMenu',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('set_name', models.CharField(max_length=100)),
                ('set_price', models.FloatField()),
                ('set_image', models.ImageField(upload_to='setmenu_images/')),
                ('booth', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='booth.booth')),
            ],
        ),
        migrations.CreateModel(
            name='SetMenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField()),
                ('menu', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='menu.menu')),
                ('set_menu', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='menu.setmenu')),
            ],
        ),
    ]
