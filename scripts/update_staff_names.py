#!/usr/bin/env python
"""
Script para actualizar los nombres del staff de StudioZens.

Nombres nuevos:
1. Natalia Verdesoto Velez
2. Maria Velez Galeano
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from users.models import CustomUser


def update_staff_names():
    """Actualiza los nombres del staff a nombres reales."""
    
    print("=" * 70)
    print("ACTUALIZACIÓN DE NOMBRES DEL STAFF")
    print("=" * 70)
    
    # 1. Obtener staff actual
    print("\n1. STAFF ACTUAL:")
    print("-" * 70)
    
    staff_members = CustomUser.objects.filter(
        role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN]
    ).order_by('created_at')
    
    if not staff_members.exists():
        print("   ⚠️  No hay miembros del staff en la base de datos")
        return
    
    for i, member in enumerate(staff_members, 1):
        print(f"   {i}. {member.first_name} {member.last_name}")
        print(f"      Email: {member.email or member.phone_number}")
        print(f"      Rol: {member.get_role_display()}")
        print(f"      ID: {member.id}")
        print()
    
    # 2. Definir nuevos nombres
    new_names = [
        {
            'first_name': 'Natalia',
            'last_name': 'Verdesoto Velez',
        },
        {
            'first_name': 'Maria',
            'last_name': 'Velez Galeano',
        },
    ]
    
    # 3. Actualizar nombres
    print("\n2. ACTUALIZANDO NOMBRES:")
    print("-" * 70)
    
    updated_count = 0
    for i, member in enumerate(staff_members[:2]):  # Solo los primeros 2
        if i < len(new_names):
            old_name = f"{member.first_name} {member.last_name}"
            
            member.first_name = new_names[i]['first_name']
            member.last_name = new_names[i]['last_name']
            member.save(update_fields=['first_name', 'last_name'])
            
            new_name = f"{member.first_name} {member.last_name}"
            
            print(f"   ✓ Actualizado:")
            print(f"      Antes: {old_name}")
            print(f"      Ahora: {new_name}")
            print(f"      Email: {member.email or member.phone_number}")
            print()
            
            updated_count += 1
    
    # 4. Verificar cambios
    print("\n3. STAFF ACTUALIZADO:")
    print("-" * 70)
    
    staff_members = CustomUser.objects.filter(
        role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN]
    ).order_by('created_at')
    
    for i, member in enumerate(staff_members, 1):
        print(f"   {i}. {member.first_name} {member.last_name}")
        print(f"      Email: {member.email or member.phone_number}")
        print(f"      Rol: {member.get_role_display()}")
        print()
    
    # 5. Resumen
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"   Miembros actualizados: {updated_count}")
    print(f"   Total staff: {staff_members.count()}")
    print("\n✅ Actualización completada exitosamente!")
    print("=" * 70)


if __name__ == '__main__':
    update_staff_names()
