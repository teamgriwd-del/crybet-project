from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from pathlib import Path
P=Path(__file__).parent
styles=getSampleStyleSheet()
styles['BodyText'].fontSize=10;styles['BodyText'].leading=14
styles['Heading1'].textColor=colors.HexColor('#123c58')
story=[]
def h(t): story.append(Paragraph(t,styles['Heading1']))
def p(t): story.append(Paragraph(t,styles['BodyText']));story.append(Spacer(1,7))
def table(rows,widths=None):
    data=[[Paragraph(str(c),styles['BodyText']) for c in r] for r in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dfedf4')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#a1b4bf')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t);story.append(Spacer(1,10))
def page():story.append(PageBreak())
h('IoT FM transmission silence detection')
p('Breadboard prototype • ESP32 DevKit V1 • ADS1115 • LM358 • BAT43 • RDA5807M')
p('<b>Purpose:</b> receive an FM station, convert its audio peaks into a slowly changing voltage, and send that measurement over Wi-Fi to a Windows PC dashboard. Silence means low audio for a configured duration; this does not prove transmitter or RF carrier failure.')
p('<b>Receiver pinout pending:</b> your receiver has not arrived and its board model is unknown. This guide assigns connections by pin <b>label/function</b>, not by physical position. Verify the module datasheet before wiring. A bare receiver IC needs its reference circuit, crystal, RF components and a suitable PCB; do not put it directly into this breakout-board layout.')
h('1. Additional parts required')
table([['Part','Quantity / use'],['Resistors','30 kΩ x1; 10 kΩ x2; 100 kΩ x2; 1 kΩ x2. Use 1% if available.'],['Capacitors','1 µF nonpolar/film x2 (audio coupling and envelope); 100 nF ceramic x3 (supply bypass); 10 µF x1 (reference filter, positive toward divider). Voltage rating 6.3 V or higher.'],['Other','Breadboard, jumpers, USB data cable, multimeter, and antenna suitable for your receiver module.'],['Main parts','One ESP32 DevKit V1, LM358 DIP-8 (or correctly mapped adapter), one BAT43 diode, one ADS1115 breakout, one documented RDA5807M breakout.'],['I²C pull-ups','Only if not fitted: 4.7 kΩ SDA to 3.3 V and 4.7 kΩ SCL to 3.3 V. Do not add blindly if both modules already have pull-ups.']],[125,375])
p('<b>Power:</b> USB powers ESP32. Use ESP32 <b>3V3</b> for this entire analog/I²C circuit; join all grounds. Do not connect USB/VIN/5V to the 3.3 V rail. Never apply 5 V logic to ESP32 or this ADS1115. Power off while changing wiring. Breadboard power rails may be split; check continuity.')
p('<b>Design limit:</b> the LM358 is not rail-to-rail. This circuit biases audio to about 0.825 V and is intended for audio peaks no larger than about ±0.4 V at LM358 pin 3 (roughly 0.425–1.225 V). Meter-check the bias and use an oscilloscope for peak/clipping checks if available. Large headphone/speaker signals are unsuitable without attenuation. Do not assume the listed parts alone make a calibrated instrument.')
page();h('2. Digital bus and power connections')
table([['From','To / purpose'],['ESP32 3V3','ADS1115 VDD/VCC; LM358 pin 8; RDA5807M breakout 3.3 V supply only if its documentation permits.'],['ESP32 GND','ADS1115 GND; LM358 pin 4; receiver GND; analog ground rail.'],['ESP32 GPIO21','ADS1115 SDA and receiver SDA / SDIO.'],['ESP32 GPIO22','ADS1115 SCL and receiver SCL / SCLK.'],['ADS1115 ADDR','GND: I²C address 0x48.'],['ADS1115 A0','Envelope E through 1 kΩ (R7). Do not use digital GPIO as the audio input.'],['ADS1115 A1/A2/A3, ALERT','Leave disconnected; firmware reads only A0.'],['Receiver LOUT / L audio','Only to C1 audio coupling capacitor below. Leave ROUT disconnected for this single-channel prototype; never short LOUT and ROUT together.'],['Receiver ANT','Antenna according to the actual module instructions. Some boards use a headphone lead as the antenna.'],['Decoupling','100 nF between supply and ground near each of LM358, ADC and receiver. Keep analog leads short.']],[145,355])
h('3. LM358 orientation — DIP-8, top view')
p('Place the DIP IC across the breadboard centre gap. With the notch at the top, pin 1 is upper left. Down the left side: <b>1 OUT A, 2 IN− A, 3 IN+ A, 4 GND</b>. Up the right side: <b>5 IN+ B, 6 IN− B, 7 OUT B, 8 V+</b>. Pins 1 and 8 are opposite each other at the notch end. Confirm the manufacturer datasheet; other packages require an adapter and may differ.')
h('4. Build the 0.825 V reference first')
p('3V3 → <b>R1 30 kΩ</b> → divider node B → <b>R2 10 kΩ</b> → GND. Put C2 10 µF from B to GND (+ to B). Connect B to LM358 pin 5. Connect LM358 pin 6 directly to pin 7. Pin 7 is <b>VREF</b>, approximately 3.3 × 10/(30+10) = 0.825 V. This uses amplifier B as a reference buffer.')
p('Check with a multimeter: pin 8 about 3.3 V; pin 4 ground; B and pin 7 about 0.825 V. Stop if these are incorrect. VREF is an analog bias, <b>not a ground rail</b>.')
page();h('5. Audio and envelope — exact net connections')
table([['Connection','Part / instruction'],['Receiver LOUT → C1 → R3 → S','C1 = 1 µF nonpolar coupling capacitor; R3 = 10 kΩ. S is the biased audio node.'],['S → VREF','R4 = 100 kΩ. This sets DC bias at the input.'],['S → LM358 pin 3','Amplifier A non-inverting input.'],['LM358 pin 2 → pin 1','Direct feedback; amplifier A is a unity-gain buffer.'],['Pin 1 → R5 → D1 anode','R5 = 1 kΩ limits charging current and isolates the capacitor load.'],['D1 cathode → E','D1 = BAT43. The cathode is the banded end. E is the envelope node.'],['E → VREF','R6 = 100 kΩ; envelope discharge path.'],['E → GND','C3 = 1 µF nonpolar. Nominal decay time R6 × C3 = 0.1 s.'],['E → R7 → ADS1115 A0','R7 = 1 kΩ. ADC and amplifier share 3.3 V and GND.']],[185,315])
p('With quiet input, E settles near VREF because R6 pulls it there. Audio peaks above VREF plus the diode drop charge C3. The ADC measures E, and the dashboard subtracts the measured quiet baseline. The BAT43 forward voltage varies with current and temperature; weak audio can fall below its useful detection range.')
class Diagram(Flowable):
    def __init__(self): Flowable.__init__(self); self.width=500;self.height=175
    def draw(self):
        c=self.canv;c.setFont('Helvetica',9)
        def line(x,y,a,b):c.line(x,y,a,b)
        def box(x,y,w,h,t):c.rect(x,y,w,h);c.drawCentredString(x+w/2,y+h/2-3,t)
        box(0,100,65,30,'LOUT');box(85,100,55,30,'C1 1uF');box(158,100,65,30,'R3 10k');box(260,100,80,30,'LM358 A');box(355,100,55,30,'R5 1k')
        for a,b in [(65,85),(140,158),(223,260),(340,355)]:line(a,115,b,115)
        line(410,115,430,115);c.drawString(415,143,'D1 BAT43');c.drawString(416,130,'A ->| K');line(430,115,495,115);c.drawString(447,100,'E -> R7 -> A0')
        line(240,115,240,65);box(207,40,66,25,'R4 100k');line(240,40,240,15);c.drawString(219,3,'VREF')
        line(460,115,460,65);box(427,40,66,25,'R6 100k');line(460,40,460,15);c.drawString(442,3,'VREF')
        c.drawString(280,75,'Pin 2 tied to pin 1');c.drawString(280,60,'S goes to pin 3');c.drawString(0,65,'C3 1uF: E to GND');c.drawString(0,45,'VREF = LM358 pin 7');c.drawString(0,25,'All GNDs connected')
story.append(Diagram())
p('<b>Analog verification:</b> before connecting ADS1115 A0, check E is near 0.825 V at quiet and remains between GND and 3.3 V. The ADC gain setting ±4.096 V is a conversion range, not permission to exceed its 3.3 V supply. The 1 kΩ resistor is not an overvoltage clamp.')
page();h('6. Bring-up before the receiver arrives')
p('1. Build only the reference circuit and check its voltages. Then build the buffer/envelope. With the receiver absent, connect the left/input side of C1 to GND. S, buffer pin 1 and E should settle near VREF. Do not ground S, VREF or a powered receiver output.')
p('2. Set <b>USE_RADIO 0</b> in the firmware for receiver-free ADC testing. Upload using the supplied README. Check readings near the measured envelope baseline. A stable quiet reading verifies bias and telemetry, not audio sensitivity.')
p('3. For a controlled audio test, disconnect the grounding jumper and apply an isolated/low-voltage signal-generator sine wave: about 1 kHz, 0.8 V peak-to-peak, zero DC offset, to the input side of C1; generator GND to common GND. Check S stays in its permitted range. E should rise by a measurable amount. Start at lower amplitude and increase gradually. Never use mains or an unknown speaker output.')
p('4. If you have no suitable audio test source, use dashboard simulation now and defer analog sound validation until the documented receiver arrives. Do not claim a silent baseline proves sound detection.')
h('7. Windows dashboard and ESP32 connection')
p('Extract the ZIP and install Python 3.10+. First run <b>py -3 server.py --create-user &quot;+YOUR_NUMBER&quot;</b> with your international phone number, then choose a password (12+ characters). Run <b>py -3 server.py --demo</b>; open <b>http://localhost:8000</b> and sign in. Simulation cycles normal, low audio, carrier/no audio and transmitter off. Stop with Ctrl+C before hardware mode.')
p('For hardware: run <b>py -3 server.py --host 0.0.0.0</b>. Put the PC Wi-Fi IPv4 address from <b>ipconfig</b> into the ESP32 SERVER_URL. Both devices must be on the same trusted LAN; ESP32 needs 2.4 GHz Wi-Fi. Permit Python on Windows Firewall Private networks only. Generate a device token using <b>py -3 server.py --create-device-token</b> and copy it into local firmware. No port forwarding: HTTP is unencrypted even with login. See README.md and HARDWARE_API.md for current setup and telemetry fields.')
p('In Arduino IDE install the Espressif ESP32 board package, Adafruit ADS1X15 and PU2CLR RDA5807 libraries. Choose DOIT ESP32 DEVKIT V1. Set Wi-Fi, PC address and local FM frequency in the sketch. Serial Monitor is 115200 baud. The full README gives upload and troubleshooting steps.')
h('8. Calibration and limitations')
p('Fix the radio volume. With a known silent input, wait 2 s and record/use the latest reading as the quiet baseline. Restore normal audio and choose a threshold above quiet noise but below measured programme levels. Defaults are silence below 45 mV rise, normal at or above 100 mV, and 5 s silence delay; calibrate all three. Low audio falls between the thresholds. Verify recovery and device offline within 3 s after telemetry stops.')
p('<b>Prototype limitations:</b> one audio channel; diode dead zone; receiver hiss may mask loss of station; carrier inference requires RSSI calibration; confirmed transmitter off needs independent hardware status; settings/history are not persistent. If quiet and programme levels overlap, this circuit is unsuitable at that level and needs amplification or a precision detector. Firmware and circuit are supplied for bench validation; Arduino compilation, actual receiver pin order and physical operation have not been verified here.')
def footer(c,d):
    c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#596879'));c.drawString(45,23,'FM silence monitor | breadboard prototype | verify actual module pinout');c.drawRightString(550,23,str(d.page))
SimpleDocTemplate(str(P/'Breadboard_Wiring.pdf'),rightMargin=45,leftMargin=45,topMargin=36,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
