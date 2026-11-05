import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private readonly n8nUrl = 'https://n8n.ahca.dev/webhook/hack4edu';
  private readonly http = inject(HttpClient);

  private enviarWebhook(bodyData: any): Observable<any> {
    const headers = new HttpHeaders({
      'Content-Type': 'application/json'
    });
    return this.http.post<any>(this.n8nUrl, bodyData, { headers });
  }

  facerRegistro(datos: any): Observable<any> {
    const body = {
      accion: "Registro",
      payload: datos
    };
    return this.enviarWebhook(body);
  }

  facerLogin(correo: string, password: string): Observable<any> {
    const body = {
      accion: "Login",
      payload: {
        password: password,
        correo: correo
      }
    };
    return this.enviarWebhook(body);
  }

  enviarConfiguracion(datos: any): Observable<any> {
    return this.enviarWebhook(datos);
  }
}