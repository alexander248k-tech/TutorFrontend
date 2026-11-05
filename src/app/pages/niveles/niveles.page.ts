import { CommonModule } from '@angular/common';
import { Component, ViewChild, inject } from '@angular/core';
import type { AfterViewInit, ElementRef, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';

import { ApiService } from '../../services/api';

@Component({
  selector: 'app-niveles',
  templateUrl: './niveles.page.html',
  styleUrls: ['./niveles.page.scss'],
  standalone: true,
  imports: [CommonModule]
})
export class NivelesPage implements OnInit, AfterViewInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly apiService = inject(ApiService);

  @ViewChild('starsCanvas') starsCanvas!: ElementRef<HTMLCanvasElement>;

  correo = '';
  nivelActual = '';
  cargando = false;

  modalAbierto = false;
  modalLevelText = '';
  modalPlanetText = '';
  modalTitleText = '';
  modalDescriptionText = '';
  mensajeEstado = '';

  private animationId = 0;
  private resizeHandler?: () => void;

  ngOnInit(): void {
    this.correo = sessionStorage.getItem('correo') || '';
    this.nivelActual = sessionStorage.getItem('nivelIngles') || sessionStorage.getItem('nivelActual') || sessionStorage.getItem('nivel') || 'A1';
  }

  ngAfterViewInit(): void {
    this.iniciarCanvasEstrellas();
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.animationId);
    if (this.resizeHandler) {
      window.removeEventListener('resize', this.resizeHandler);
    }
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
    this.resizeHandler = resize;
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
      this.animationId = requestAnimationFrame(draw);
    };
    draw();
  }

  openModal(nivel: string, planeta: string, titulo: string, descripcion: string): void {
    this.modalLevelText = nivel;
    this.modalPlanetText = planeta;
    this.modalTitleText = titulo;
    this.modalDescriptionText = descripcion;
    this.mensajeEstado = '';
    this.modalAbierto = true;
  }

  closeModal(): void {
    this.modalAbierto = false;
  }

  confirmarNivel(): void {
    const nuevoNivel = this.modalLevelText;
    this.cargando = true;
    this.mensajeEstado = 'Sincronizando nivel con el sistema estelar...';

    sessionStorage.setItem('nivelIngles', nuevoNivel);
    sessionStorage.setItem('nivelActual', nuevoNivel);
    sessionStorage.setItem('nivel', nuevoNivel);
    this.nivelActual = nuevoNivel;

    const payloadNivel = {
      accion: "Configuracion",
      editar: "ActualizarNivel",
      payload: {
        correo: this.correo,
        NivelIngels: nuevoNivel
      }
    };

    console.log('Enviando actualización de nivel exacta a n8n:', payloadNivel);

    this.apiService.enviarConfiguracion(payloadNivel).subscribe({
      next: (res: any) => {
        console.log('Nivel actualizado correctamente en n8n:', res);
        this.cargando = false;
        this.mensajeEstado = '✨ ¡Nivel actualizado con éxito!';
        
        setTimeout(() => {
          this.closeModal();
          void this.router.navigate(['/chat']);
        }, 1200);
      },
      error: (err: any) => {
        console.warn('Aviso al actualizar nivel en n8n:', err);
        this.cargando = false;
        this.mensajeEstado = '⚠️ Guardado localmente. Redirigiendo al chat...';

        setTimeout(() => {
          this.closeModal();
          void this.router.navigate(['/chat']);
        }, 1500);
      }
    });
  }

  regresarMenu(): void {
    void this.router.navigate(['/menu']);
  }
}