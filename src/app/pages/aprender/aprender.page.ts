import { CommonModule } from '@angular/common';
import type { AfterViewInit, ElementRef, OnDestroy, OnInit } from '@angular/core';
import { ChangeDetectorRef, Component, ViewChild, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TimeoutError, finalize, timeout } from 'rxjs';

import { ApiService } from '../../services/api';

@Component({
  selector: 'app-aprender',
  templateUrl: './aprender.page.html',
  styleUrls: ['./aprender.page.scss'],
  standalone: true,
  imports: [CommonModule, FormsModule]
})
export class AprenderPage implements OnInit, AfterViewInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly apiService = inject(ApiService);
  private readonly cdr = inject(ChangeDetectorRef);

  @ViewChild('starsCanvas') starsCanvas!: ElementRef<HTMLCanvasElement>;

  correo = '';
  usuario = '';
  nivelIngles = '';
  temaSeleccionado = '';
  cargando = false;
  cargandoTemas = true;

  fase: 'seleccion' | 'ejercicio' | 'resultado' = 'seleccion';

  ejercicioTexto = '';

  actividadPendiente = false;

  
  respuesta1 = '';

  resultadoEvaluacion = '';

  
  private readonly TIMEOUT_MS = 90000;

  private todosLosTemasNiveles: Record<string, { nivel: string; nombre: string; temas: string[] }> = {
    'A1': {
      nivel: 'Nivel A1',
      nombre: 'Empezar desde cero',
      temas: [
        'Saludos y presentaciones',
        'Alfabeto y deletreo',
        'Números, fechas y hora',
        'Pronombres y verbo to be',
        'Vocabulario esencial',
        'Artículos y plurales',
        'Presente simple',
        'Preguntas básicas'
      ]
    },
    'A2': {
      nivel: 'Nivel A2',
      nombre: 'Comunicación cotidiana',
      temas: [
        'Presente continuo',
        'Can / can’t',
        'Pasado simple',
        'Pasado de to be',
        'There is / There are',
        'Comparativos y superlativos',
        'Some / any, much / many',
        'Futuro básico',
        'Vocabulario funcional (Restaurante, transporte, compras, médico y direcciones)'
      ]
    },
    'B1': {
      nivel: 'Nivel B1',
      nombre: 'Independencia',
      temas: [
        'Present perfect',
        'Present perfect vs. past simple',
        'Pasado continuo',
        'Condicionales 0 y 1',
        'Verbos modales',
        'Voz pasiva básica',
        'Discurso indirecto I',
        'Conectores',
        'Vocabulario intermedio (Trabajo, tecnología, salud, viajes y educación)'
      ]
    },
    'B2': {
      nivel: 'Nivel B2',
      nombre: 'Intermedio alto',
      temas: [
        'Tiempos verbales completos',
        'Condicionales 2 y 3',
        'Voz pasiva avanzada',
        'Discurso indirecto II',
        'Cláusulas relativas',
        'Phrasal verbs',
        'Modismos frecuentes',
        'Escritura formal',
        'Debate y opinión'
      ]
    }
  };

  temasVisibles: { nivel: string; nombre: string; temas: string[] }[] = [];

  private animationId = 0;
  private resizeHandler?: () => void;

  ngOnInit(): void {
    this.correo = sessionStorage.getItem('correo') || 'test@gmail.com';
    this.usuario = sessionStorage.getItem('usuario') || 'Hacker kitty';
    this.nivelIngles =
      sessionStorage.getItem('nivelIngles') ||
      sessionStorage.getItem('nivelActual') ||
      sessionStorage.getItem('nivel') ||
      'A1';

   
    this.filtrarTemasPorNivel(this.nivelIngles);
    this.solicitarInfoNivelBackend();
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

  
  private extraerTexto(res: any, campos: string[]): string {
    let data = res;

    if (typeof data === 'string') {
      const limpio = data.trim();
      try {
        data = JSON.parse(limpio);
      } catch {
        return this.normalizarSaltos(limpio);
      }
    }

    if (Array.isArray(data)) {
      data = data[0];
    }

    if (typeof data === 'string') return this.normalizarSaltos(data);
    if (!data || typeof data !== 'object') return '';

    let texto: any = '';
    for (const campo of campos) {
      if (data[campo] !== undefined && data[campo] !== null && data[campo] !== '') {
        texto = data[campo];
        break;
      }
    }

    if (typeof texto === 'object') {
      texto = JSON.stringify(texto, null, 2);
    }

    return this.normalizarSaltos(String(texto));
  }

  
  private normalizarClave(clave: string): string {
    return clave
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]/g, '');
  }

 
  private obtenerInfo(res: any): Record<string, any> | null {
    let data = res;
    if (typeof data === 'string') {
      try {
        data = JSON.parse(data);
      } catch {
        return null;
      }
    }
    if (Array.isArray(data)) data = data[0];
    return data && typeof data === 'object' ? data : null;
  }

  private esNivel(valor: unknown): boolean {
    return typeof valor === 'string' && /^[abc][12]$/i.test(valor.trim());
  }

  
  private extraerNivel(res: any): string {
    const info = this.obtenerInfo(res);
    if (!info) return '';
    const clavesNivel = ['nivelingles', 'nivel', 'nivelingels', 'nivelactual'];
    for (const clave of Object.keys(info)) {
      if (clavesNivel.includes(this.normalizarClave(clave)) && this.esNivel(info[clave])) {
        return String(info[clave]).trim().toUpperCase();
      }
    }
    return '';
  }

 
  private valorATextoActividad(valor: any): string {
    if (valor === undefined || valor === null || typeof valor === 'boolean') return '';

    let v = valor;
    if (Array.isArray(v)) {
      v = v
        .map((x: any) => (typeof x === 'string' ? x : (x?.ejercicio ?? x?.texto ?? JSON.stringify(x))))
        .join('\n');
    } else if (typeof v === 'object') {
      v = v.ejercicio ?? v.texto ?? v.ejerciciosLimpios ?? JSON.stringify(v, null, 2);
    }

    const texto = this.normalizarSaltos(String(v));
    const vacio = ['', 'null', 'none', 'ninguno', 'ninguna', 'sin pendientes', 'no', 'false', '[]', '{}', 'n/a'];
    return vacio.includes(texto.toLowerCase().trim()) ? '' : texto;
  }

  
  private extraerActividadPendiente(res: any): string {
    const info = this.obtenerInfo(res);
    if (!info) return '';

    const clavesActividad = [
      'ejerciciopendiente',
      'actividadpendiente',
      'actividadespendientes',
      'pendiente',
      'pendientes',
      'ejercicioslimpios',
      'ejercicio',
      'ejercicios',
      'actividades'
    ];
    const clavesNivel = ['nivelingles', 'nivel', 'nivelingels', 'nivelactual'];

   
    for (const clave of Object.keys(info)) {
      if (clavesActividad.includes(this.normalizarClave(clave))) {
        const texto = this.valorATextoActividad(info[clave]);
        if (texto) return texto;
      }
    }

    
    for (const clave of Object.keys(info)) {
      if (clavesNivel.includes(this.normalizarClave(clave)) && !this.esNivel(info[clave])) {
        const texto = this.valorATextoActividad(info[clave]);
        if (texto) return texto;
      }
    }

    return '';
  }

  
  private normalizarSaltos(texto: string): string {
    let t = texto.trim();
    if (t.startsWith('"') && t.endsWith('"')) {
      try {
        t = JSON.parse(t);
      } catch {
        t = t.slice(1, -1);
      }
    }
    return t.replace(/\\n/g, '\n');
  }

  private refrescar(): void {
    
    this.cdr.detectChanges();
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

  

  solicitarInfoNivelBackend(): void {
    this.cargandoTemas = true;

    const payloadInfo = {
      accion: 'Configuracion',
      editar: 'PedirInfo',
      payload: {
        correo: this.correo
      }
    };

    this.apiService
      .enviarConfiguracion(payloadInfo)
      .pipe(
        timeout(20000),
        finalize(() => {
          this.cargandoTemas = false;
          this.refrescar();
        })
      )
      .subscribe({
        next: (res: any) => {
          console.log('Info del usuario (PedirInfo):', res);

         
          const nivelObtenido = this.extraerNivel(res);
          if (nivelObtenido) {
            this.nivelIngles = nivelObtenido;
            sessionStorage.setItem('nivelIngles', this.nivelIngles);
            sessionStorage.setItem('nivelActual', this.nivelIngles);
          }
          this.filtrarTemasPorNivel(this.nivelIngles);

         
          const pendiente = this.extraerActividadPendiente(res);
          if (pendiente) {
            this.ejercicioTexto = pendiente;
            this.actividadPendiente = true;
            this.respuesta1 = '';
            this.fase = 'ejercicio';
          }
        },
        error: () => {
          this.filtrarTemasPorNivel(this.nivelIngles);
        }
      });
  }

  private filtrarTemasPorNivel(nivel: string): void {
    const nivelKey = nivel.toUpperCase().trim();
    const datosNivel = this.todosLosTemasNiveles[nivelKey] || this.todosLosTemasNiveles['A1'];
    this.temasVisibles = [datosNivel];
  }

  seleccionarTema(tema: string): void {
    this.temaSeleccionado = tema;
  }

  

  enviarTema(): void {
    if (!this.temaSeleccionado.trim() || this.cargando) return;

    this.cargando = true;
    this.ejercicioTexto = 'Sintetizando ejercicios estelares...';

    const payloadN8N = {
      tema: this.temaSeleccionado,
      accion: 'Pregunta',
      Pregunta: `quiero aprender ${this.temaSeleccionado}`,
      payload: {
        correo: this.correo
      }
    };

    console.log('Enviando tema a n8n:', payloadN8N);

    this.apiService
      .enviarConfiguracion(payloadN8N)
      .pipe(
        timeout(this.TIMEOUT_MS),
        finalize(() => {
          this.cargando = false;
          this.refrescar();
        })
      )
      .subscribe({
        next: (res: any) => {
          console.log('Preguntas recibidas de n8n:', res);

          const texto = this.extraerTexto(res, [
            'ejerciciosLimpios',
            'ejercicio',
            'mensaje',
            'respuesta',
            'output'
          ]);

          this.ejercicioTexto = texto || 'No recibí ejercicios. Intenta de nuevo.';

         
          this.respuesta1 = '';
          this.fase = 'ejercicio';
        },
        error: (err: any) => {
          console.error('Error al conectar con n8n:', err);
          this.ejercicioTexto =
            err instanceof TimeoutError
              ? '⏱️ El servidor estelar tardó demasiado. Intenta de nuevo.'
              : '⚠️ Error al conectar con el servidor estelar. Intenta de nuevo.';
        }
      });
  }

 
  get respuestasCompletas(): boolean {
    return !!this.respuesta1.trim();
  }

  enviarRespuestas(): void {
    if (this.cargando || !this.respuestasCompletas) return;

    this.cargando = true;
    this.resultadoEvaluacion = 'Evaluando tus respuestas estelares...';

    
    const payloadRespuestas = {
      accion: 'Pregunta',
      payload: {
        correo: this.correo,
        respuesta1: this.respuesta1.trim()
      }
    };

    console.log('Enviando respuestas a n8n:', payloadRespuestas);

    this.apiService
      .enviarConfiguracion(payloadRespuestas)
      .pipe(
        timeout(this.TIMEOUT_MS),
        finalize(() => {
          this.cargando = false;
          this.refrescar();
        })
      )
      .subscribe({
        next: (res: any) => {
          console.log('Resultado de evaluación recibido:', res);

          const texto = this.extraerTexto(res, [
            'resultado',
            'ejercicio',
            'ejerciciosLimpios',
            'evaluacion',
            'mensaje',
            'respuesta',
            'output'
          ]);

          this.resultadoEvaluacion = texto || 'Respuestas recibidas por NOVA.';
          this.actividadPendiente = false;
          this.fase = 'resultado';
        },
        error: (err: any) => {
          console.error('Error al enviar respuestas:', err);
          this.resultadoEvaluacion =
            err instanceof TimeoutError
              ? '⏱️ NOVA tardó demasiado en evaluar. Intenta de nuevo.'
              : '⚠️ Error al enviar respuestas al servidor estelar.';
          this.fase = 'resultado';
        }
      });
  }

  reiniciarLeccion(): void {
    this.fase = 'seleccion';
    this.actividadPendiente = false;
    this.temaSeleccionado = '';
    this.respuesta1 = '';
    this.ejercicioTexto = '';
    this.resultadoEvaluacion = '';
  }

  regresarMenu(): void {
    void this.router.navigate(['/menu']);
  }
}