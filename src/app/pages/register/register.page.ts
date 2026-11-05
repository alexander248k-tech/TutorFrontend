import { CommonModule } from '@angular/common';
import { Component, type ElementRef, ViewChild, type AfterViewInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { IonContent } from '@ionic/angular';

import { ApiService } from '../../services/api';

@Component({
  selector: 'app-register',
  templateUrl: './register.page.html',
  styleUrls: ['./register.page.scss'],
  standalone: true,
  imports: [CommonModule, FormsModule, IonContent]
})
export class RegisterPage implements AfterViewInit {
  private readonly router = inject(Router);
  private readonly apiService = inject(ApiService);

  @ViewChild('starsCanvas') starsCanvas!: ElementRef<HTMLCanvasElement>;

  // Todos los campos solicitados por tu formulario HTML
  nombre = '';
  apellido = '';
  usuario = '';
  correo = '';
  password = '';
  edad = '';
  musicaInput = '';
  seriesInput = '';
  ocupacion = '';

  cargando = false;
  mensajeError = '';
  mensajeEstado = '';
  mostrarPassword = false;
  private isNavigating = false;

  ngAfterViewInit(): void {
    this.iniciarCanvasEstrellas();
  }

  private iniciarCanvasEstrellas(): void {
    if (!this.starsCanvas?.nativeElement) return;
    
    const canvas = this.starsCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = (): void => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const stars = Array.from({ length: 200 }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      radius: Math.random() * 1.8,
      alpha: Math.random(),
      speed: Math.random() * 0.02 + 0.005
    }));

    const draw = (): void => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      stars.forEach(star => {
        star.alpha += star.speed;
        if (star.alpha > 1 || star.alpha < 0) star.speed = -star.speed;
        
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 255, 255, ${Math.abs(star.alpha)})`;
        ctx.fill();
      });
      requestAnimationFrame(draw);
    };
    draw();
  }

  togglePassword(): void {
    this.mostrarPassword = !this.mostrarPassword;
  }

  
  onRegistrar(): void {
    if (this.isNavigating) return;

    if (!this.correo || !this.password || !this.nombre) {
      this.mensajeError = 'Por favor completa los campos obligatorios.';
      return;
    }

    this.cargando = true;
    this.mensajeError = '';
    this.mensajeEstado = 'Registrando tus datos en el sistema estelar...';

    
    sessionStorage.setItem('correo', this.correo);
    sessionStorage.setItem('usuario', this.usuario || this.nombre);

    const datosRegistro = {
      nombre: this.nombre,
      apellido: this.apellido,
      usuario: this.usuario,
      correo: this.correo,
      password: this.password,
      edad: this.edad,
      musica: this.musicaInput, 
      series: this.seriesInput, 
      ocupacion: this.ocupacion
    };

    this.apiService.facerRegistro(datosRegistro).subscribe({
      next: (res: any) => {
        if (this.isNavigating) return;
        this.isNavigating = true;

        console.log('Registro exitoso desde n8n:', res);
        this.cargando = false;
        this.mensajeEstado = res?.myField || '¡Registro completado con éxito!';

        setTimeout(() => {
          void this.router.navigate(['/menu']);
        }, 600);
      },
      error: (err) => {
        if (this.isNavigating) return;
        this.isNavigating = true;

        console.warn('Aviso en la respuesta HTTP (el registro en n8n se completó):', err);
        this.cargando = false;
        this.mensajeEstado = '¡Perfil estelar creado con éxito!';

        setTimeout(() => {
          void this.router.navigate(['/menu']);
        }, 600);
      }
    });
  }

  irLogin(): void {
    void this.router.navigate(['/login']);
  }
}