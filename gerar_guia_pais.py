#!/usr/bin/env python3
"""Gera o PDF 'Guia para Pais - Telefone Fixo para Criancas'."""

from fpdf import FPDF


class GuiaPDF(FPDF):
    def footer(self):
        pass


def draw_box(pdf, x, y, w, h, title, subtitle, color):
    pdf.set_fill_color(*color)
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h, style='DF')
    pdf.set_xy(x, y + 2)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(w, 5, title, align='C')
    pdf.set_xy(x, y + 7)
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(w, 4, subtitle, align='C')


def draw_arrow(pdf, x1, y, x2):
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.4)
    pdf.line(x1, y, x2, y)
    pdf.line(x2 - 2, y - 1.5, x2, y)
    pdf.line(x2 - 2, y + 1.5, x2, y)


def gerar():
    pdf = GuiaPDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_margins(15, 12, 15)
    pdf.add_page()

    # Titulo
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 10, 'Telefone Fixo para Criancas', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, 'Telefone com fio de verdade. Sem tela, sem internet, so conversa.', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(8)

    # === Esquema ===
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 7, 'Como funciona:', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    y = pdf.get_y()
    bw = 32  # largura das caixas
    bh = 14  # altura das caixas
    gap = 8  # espaco entre caixas
    # Centralizar 4 caixas + 3 gaps
    total_w = 4 * bw + 3 * gap
    x0 = (pdf.w - total_w) / 2

    # Caixas da linha principal
    boxes = [
        (x0, 'Telefone', 'seu filho', (230, 245, 230)),
        (x0 + bw + gap, 'Caixinha', 'no roteador', (220, 235, 250)),
        (x0 + 2 * (bw + gap), 'Servidor', 'na nuvem', (255, 235, 210)),
        (x0 + 3 * (bw + gap), 'Telefone', 'do amigo', (230, 245, 230)),
    ]
    for bx, title, sub, color in boxes:
        draw_box(pdf, bx, y, bw, bh, title, sub, color)

    # Setas entre caixas
    mid_y = y + bh / 2
    for i in range(3):
        ax1 = x0 + (i + 1) * bw + i * gap
        ax2 = ax1 + gap
        draw_arrow(pdf, ax1, mid_y, ax2)

    # Celular do pai
    cel_y = y + bh + 4
    draw_box(pdf, x0, cel_y, bw, bh, 'Seu celular', 'portal web', (240, 235, 250))

    # Seta diagonal celular -> servidor
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.4)
    srv_x = x0 + 2 * (bw + gap)
    pdf.line(x0 + bw, cel_y + bh / 2, srv_x, y + bh)
    # Ponta da seta
    pdf.line(srv_x - 3, y + bh - 1, srv_x, y + bh)
    pdf.line(srv_x - 3, y + bh + 2, srv_x, y + bh)

    # Texto ao lado da seta
    pdf.set_font('Helvetica', 'I', 7)
    pdf.set_text_color(140, 140, 140)
    pdf.set_xy(x0 + bw + 4, cel_y + 2)
    pdf.cell(50, 4, 'horarios, contatos, historico')

    pdf.set_y(cel_y + bh + 8)

    # Resumo
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 5,
        'A crianca usa um telefone com fio normal, conectado numa caixinha '
        'ligada no seu roteador. Voce controla tudo pelo celular.'
    )
    pdf.ln(6)

    # === Passo a passo ===
    pdf.set_draw_color(220, 220, 220)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(6)

    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 8, 'Passo a passo', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    steps = [
        ('1', 'Montar', [
            'Cabo de rede da caixinha no roteador Wi-Fi',
            'Telefone na porta de cima da caixinha (PHONE 1)',
            'Caixinha na tomada, esperar 1 minuto',
        ]),
        ('2', 'Ativar', [
            'No celular: telefone-fixo.duckdns.org/ativar',
            'Digitar o codigo de registro que voce recebeu',
            'Criar conta com email e senha',
        ]),
        ('3', 'Autorizar amigos', [
            'No portal, aba Contatos: autorize os amigos',
            'O pai do outro lado tambem precisa autorizar',
            'Quando ambos autorizarem, podem se ligar!',
        ]),
        ('4', 'Ligar!', [
            'Tirar o telefone do gancho e discar:',
            None,  # placeholder para o destaque
            '',
        ]),
    ]

    circle_r = 5
    text_x = 40

    for num, titulo, linhas in steps:
        y0 = pdf.get_y()

        # Circulo numerado
        cx = 24
        cy = y0 + circle_r
        pdf.set_fill_color(52, 152, 219)
        pdf.ellipse(cx - circle_r, cy - circle_r, circle_r * 2, circle_r * 2, style='F')
        pdf.set_xy(cx - circle_r, cy - circle_r + 1)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(circle_r * 2, circle_r * 2 - 2, num, align='C')

        # Titulo
        pdf.set_xy(text_x, y0)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 7, titulo)
        pdf.ln(8)

        # Linhas
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(80, 80, 80)
        for linha in linhas:
            if linha is None:
                # Destaque do numero
                pdf.set_x(text_x)
                pdf.set_font('Courier', 'B', 12)
                pdf.set_text_color(52, 152, 219)
                pdf.cell(0, 7, 'numero do amigo + #     (ex: 067#)', new_x='LMARGIN', new_y='NEXT')
                pdf.set_font('Helvetica', '', 9)
                pdf.set_text_color(80, 80, 80)
            elif linha:
                pdf.set_x(text_x)
                pdf.cell(0, 5.5, linha, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(5)

    # === Dica importante ===
    pdf.ln(2)
    pdf.set_draw_color(220, 220, 220)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 6, 'Bom saber:', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)

    dicas = [
        'Se nao configurar horarios, o telefone funciona o dia todo.',
        'O # no final e importante! Sem ele demora para completar.',
        'Se o telefone nao funciona, verifique se esta na porta de cima (PHONE 1).',
    ]
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(90, 90, 90)
    for d in dicas:
        pdf.set_x(pdf.l_margin + 4)
        pdf.cell(0, 5.5, '- ' + d, new_x='LMARGIN', new_y='NEXT')

    # Rodape
    pdf.ln(8)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 4, 'Duvidas? Fale com o Daniel.  |  telefone-fixo.duckdns.org', align='C')

    # Salvar
    path = '/home/daniel/daniel Dropbox/Daniel Mariani/telefone_fixo/guia-pais-telefone-fixo.pdf'
    pdf.output(path)
    print(f'PDF gerado: {path}')


if __name__ == '__main__':
    gerar()
