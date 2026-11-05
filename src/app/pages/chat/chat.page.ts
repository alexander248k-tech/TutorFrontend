import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, type ElementRef, ViewChild, type AfterViewInit, inject, type OnInit, type OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { IonContent, IonHeader, IonToolbar, IonFooter } from '@ionic/angular';
import { TimeoutError, finalize, timeout } from 'rxjs';

import { ApiService } from '../../services/api';

interface Mensaje {
  remitente: 'user' | 'nova';
  texto: string;
  hora: string;
}

@Component({
  selector: 'app-chat',
  templateUrl: './chat.page.html',
  styleUrls: ['./chat.page.scss'],
  standalone: true,
  imports: [CommonModule, FormsModule, IonContent, IonHeader, IonToolbar, IonFooter]
})
export class ChatPage implements OnInit, AfterViewInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly apiService = inject(ApiService);
  private readonly cdr = inject(ChangeDetectorRef);

  @ViewChild('starsCanvas') starsCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild(IonContent) content!: IonContent;

  usuario = '';
  nivelIngles = '';
  correo = '';
  mensajeTexto = '';
  cargando = false;

  mensajes: Mensaje[] = [];

  private animationId = 0;
  private resizeHandler?: () => void;
  private readonly TIMEOUT_MS = 90000;

  ngOnInit(): void {
    this.usuario = sessionStorage.getItem('usuario') || 'Hacker';
    this.nivelIngles = sessionStorage.getItem('nivelIngles') || sessionStorage.getItem('nivelActual') || 'A1';
    this.correo = sessionStorage.getItem('correo') || '';

    this.mensajes.push({
      remitente: 'nova',
      texto: `¡Hola ${this.usuario}! Soy NOVA, tu tutora de IA. Veo que estás en nivel ${this.nivelIngles}. ¿De qué te gustaría hablar o practicar hoy?`,
      hora: this.horaActual()
    });
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

  private horaActual(): string {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

  private extraerTexto(res: any): string {
    let data = res;

    if (typeof data === 'string') {
      const limpio = data.trim();
      try {
        data = JSON.parse(limpio);
      } catch {
        return limpio;
      }
    }

    if (Array.isArray(data)) {
      data = data[0];
    }

    if (typeof data === 'string') return data;
    if (!data || typeof data !== 'object') return '';

    let texto =
      data.mensaje ??
      data.ejerciciosLimpios ??
      data.output ??
      data.respuesta ??
      data.nombre ??
      data.myField ??
      data.text ??
      '';

    if (typeof texto === 'string') {
      const t = texto.trim();
      if (t.startsWith('"') && t.endsWith('"')) {
        try {
          texto = JSON.parse(t);
        } catch {
          /*  */
        }
      }
    } else if (typeof texto === 'object') {
      texto = JSON.stringify(texto);
    }

    return String(texto);
  }

  private agregarMensajeNova(texto: string): void {
    this.mensajes.push({
      remitente: 'nova',
      texto,
      hora: this.horaActual()
    });
    this.cdr.detectChanges();
    this.scrollToBottom();
  }

  enviarMensaje(): void {
    if (!this.mensajeTexto.trim() || this.cargando) return;

    const textoUsuario = this.mensajeTexto.trim();

    this.mensajes.push({
      remitente: 'user',
      texto: textoUsuario,
      hora: this.horaActual()
    });

    this.mensajeTexto = '';
    this.scrollToBottom();
    this.cargando = true;

    const payloadChat = {
      accion: 'Ayuda',
      correo: this.correo,
      pregunta: textoUsuario
    };

    console.log('Enviando mensaje a n8n:', payloadChat);

    this.apiService
      .enviarConfiguracion(payloadChat)
      .pipe(
        timeout(this.TIMEOUT_MS),
        finalize(() => {
          this.cargando = false;
          this.cdr.detectChanges();
        })
      )
      .subscribe({
        next: (res: any) => {
          console.log('Respuesta cruda del chat de n8n:', res);
          const texto = this.extraerTexto(res);
          this.agregarMensajeNova(texto || '¡Respuesta recibida en el sistema estelar!');
        },
        error: (err: any) => {
          console.warn('Aviso en la respuesta del chat:', err);

          if (err instanceof TimeoutError) {
            this.agregarMensajeNova('⏱️ NOVA tardó demasiado en responder. Intenta de nuevo.');
            return;
          }

          if (err?.status === 200 && typeof err?.error?.text === 'string') {
            this.agregarMensajeNova(this.extraerTexto(err.error.text));
            return;
          }

          if (err?.status === 0) {
            this.agregarMensajeNova('⚠️ No pude conectar con el servidor (posible problema de red).');
            return;
          }

          const textoError = err?.error ? this.extraerTexto(err.error) : '';
          this.agregarMensajeNova(
            textoError || `⚠️ Error del servidor estelar (código ${err?.status ?? 'desconocido'}).`
          );
        }
      });
  }

  scrollToBottom(): void {
    setTimeout(() => {
      void this.content?.scrollToBottom(300);
    }, 100);
  }

  regresarMenu(): void {
    void this.router.navigate(['/menu']);
  }
}