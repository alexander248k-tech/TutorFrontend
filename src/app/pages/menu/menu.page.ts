import { CommonModule } from '@angular/common';
import { Component, type ElementRef, ViewChild, type AfterViewInit, inject, type OnInit, type OnDestroy } from '@angular/core';
import { Router } from '@angular/router';
import { IonContent, IonHeader, IonToolbar } from '@ionic/angular';

@Component({
  selector: 'app-menu',
  templateUrl: './menu.page.html',
  styleUrls: ['./menu.page.scss'],
  standalone: true,
  imports: [CommonModule, IonContent, IonHeader, IonToolbar]
})
export class MenuPage implements OnInit, AfterViewInit, OnDestroy {
  private readonly router = inject(Router);

  @ViewChild('starsCanvas') starsCanvas!: ElementRef<HTMLCanvasElement>;

  usuario = '';
  nivelIngles = '';
  iniciales = '';

  private animationId = 0;
  private resizeHandler?: () => void;

  ngOnInit(): void {
    this.usuario = sessionStorage.getItem('usuario') || 'Hacker';
    this.nivelIngles = sessionStorage.getItem('nivelIngles') || sessionStorage.getItem('nivelActual') || 'A1';
    

    const partes = this.usuario.trim().split(' ');
    if (partes.length > 1) {
      this.iniciales = (partes[0][0] + partes[1][0]).toUpperCase();
    } else {
      this.iniciales = this.usuario.substring(0, 2).toUpperCase();
    }
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

  irChat(): void {
    void this.router.navigate(['/chat']);
  }

  irNiveles(): void {
    void this.router.navigate(['/niveles']);
  }

  irAprender(): void {
    void this.router.navigate(['/aprender']);
  }
}