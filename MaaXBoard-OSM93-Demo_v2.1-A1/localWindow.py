import os
import gi
import cairo
import threading
import cv2
import numpy
import datetime
from math import pi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from CanTools.car_attributes_handler import CarAttributesHandler


scriptFolder = os.path.dirname(__file__)
layoutPath = "resources/mainApp.glade"
globalFrame = None
cameraOpen = False
activeDemo = 0
carSpeed = 0

GladeBuilder = Gtk.Builder()

class localWindow():
    def __init__(self, callback = None):
        self.eventHandler = self.Handler(self)
        self.running = True
        self.frame = None

        self.rom = None
        self.repCount = None
        self.name = None
        self.status = None

        self.attention_status = None
        self.yawning_status = None
        self.eye_status = None
        self.inference_speed = None
        self.penalty_score = None
        self.phone_detected = None

        self.enableNPU = False

        self.car_accelerate = False
        self.car_brake = True
        self.car_attributes_handler = CarAttributesHandler()
        self.car_attributes_handler.add_speed_callback(self.UpdateCarSpeed)

        self.aboutWindow = None
        self.MainWindow = None
        self.clickCallback = callback
        self.loaclAppThread = threading.Thread(target=self.localApp)
        self.loaclAppThread.start()

    def updateFrame(self,frame):
        global globalFrame
        global cameraOpen

        globalFrame = frame
        cameraOpen = True

    def UpdateActiveDemo(self, demoIndex):
        global activeDemo
        activeDemo = demoIndex

    def UpdateCarSpeed(self, speed, rpm, throttle):
        global carSpeed
        carSpeed = speed

    def ToggleNPUAccelerationLabel(self):
        if self.enableNPU == False:
            self.enableNPU = True
        else:
            self.enableNPU = False

    def UpdateFitnessUI(self, rom, repCount, name, status):
        GLib.idle_add(self.update_FitnessUI_elements, rom, repCount, name, status)

    def UpdateDMSUI(self, attention_status, yawning_status, eye_status, inference_speed, penalty_score, phone_detected):
        GLib.idle_add(self.update_DMSUI_elements, attention_status, yawning_status, eye_status, inference_speed, penalty_score, phone_detected)

    def UpdateCANUI(self):
        GLib.idle_add(self.update_CANUI_elements)

    def ReportClick(self, event):
        self.clickCallback(event)

    def update_FitnessUI_elements(self, rom, repCount, name, status):
        label1 = GladeBuilder.get_object("Demo1_label1")
        label2 = GladeBuilder.get_object("Demo1_label2")
        label3 = GladeBuilder.get_object("Demo1_label3")
        progress = GladeBuilder.get_object("progress_bar")

        if (self.name != name):

            label1.set_label("Exercise: " + str(name))
            self.name = name

        if (self.repCount != repCount):

            label2.set_label("Repetitions: " +str(repCount))
            self.repCount = repCount

        if (self.status != status):

            if str(status) == "Good Landmark Detection":
                label3_text = '<span foreground="#00ff00" size="xx-large">Status: {}</span>'.format(str(status))
                label3.set_markup(label3_text)
            else:
                label3_text = '<span foreground="#ff0000" size="xx-large">Status: {}</span>'.format(str(status))
                label3.set_markup(label3_text)
            self.status = status

        if (self.rom != rom):
            progress.set_fraction(rom / 100)
            self.rom = rom

    def update_DMSUI_elements(self, attention_status, yawning_status, eye_status, inference_speed, penalty_score, phone_detected):

        label1 = GladeBuilder.get_object("Demo2_label1")
        label2 = GladeBuilder.get_object("Demo2_label2")
        label3 = GladeBuilder.get_object("Demo2_label3")
        label4 = GladeBuilder.get_object("inference_speed_label")
        label5 = GladeBuilder.get_object("npu_enable_label")
        label6 = GladeBuilder.get_object("penalty_label")
        label7 = GladeBuilder.get_object("phone_detect_label")
        penalty_image = GladeBuilder.get_object("penalty_image")

        if (self.attention_status != attention_status):
            if attention_status != "Forward":
                label1_text = '<span weight="bold" foreground="#ff0000" size="xx-large">{}</span>'.format(str(attention_status))
                label1.set_markup(label1_text)
            else:
                label1_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("Forward"))
                label1.set_markup(label1_text)
            self.attention_status = attention_status

        if (self.yawning_status != yawning_status):

            if yawning_status == True:
                label2_text = '<span weight="bold" foreground="#ff0000" size="xx-large">{}</span>'.format(str("Yes"))
                label2.set_markup(label2_text)
            else:
                label2_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("No"))
                label2.set_markup(label2_text)
            self.yawning_status = yawning_status

        if (self.eye_status != eye_status):
            if eye_status == True:
                label3_text = '<span weight="bold" foreground="#ff0000" size="xx-large">{}</span>'.format(str("Closed"))
                label3.set_markup(label3_text)
            else:
                label3_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("Open"))
                label3.set_markup(label3_text)
            self.eye_status = eye_status

        if (self.phone_detected != phone_detected):
            if phone_detected == True:
                label7_text = '<span weight="bold" foreground="#ff0000" size="xx-large">{}</span>'.format(str("Yes"))
                label7.set_markup(label7_text)
            else:
                label7_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("No"))
                label7.set_markup(label7_text)
            self.phone_detected = phone_detected

        if (self.inference_speed != inference_speed):
            label4_text = '<span weight="bold" size="xx-large">{}</span>'.format(str(inference_speed + " ms"))
            label4.set_markup(label4_text)
            self.inference_speed = inference_speed

        if (self.penalty_score != penalty_image):
            if penalty_score < 15:
                label6_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("OK"))
                label6.set_markup(label6_text)
                penalty_image.set_from_file(scriptFolder + "/resources/green_triangle.png")
            if penalty_score > 40:
                label6_text = '<span weight="bold" foreground="#ffff00" size="xx-large">{}</span>'.format(str("Warning"))
                label6.set_markup(label6_text)
                penalty_image.set_from_file(scriptFolder + "/resources/yellow_triangle.png")
            if penalty_score > 75:
                label6_text = '<span weight="bold" foreground="#ff0000" size="xx-large">{}</span>'.format(str("Alert"))
                label6.set_markup(label6_text)
                penalty_image.set_from_file(scriptFolder + "/resources/red_triangle.png")


        if self.enableNPU == False:
            label5_text = '<span weight="bold" foreground="#ffff00" size="xx-large">{}</span>'.format(str("CPU"))
            label5.set_markup(label5_text)
        else:
            label5_text = '<span weight="bold" foreground="#00ff00" size="xx-large">{}</span>'.format(str("NPU"))
            label5.set_markup(label5_text)

    def update_CANUI_elements(self):
        # grab objects
        gas_pedal_image = GladeBuilder.get_object("gas_pedal")
        brake_pedal_image = GladeBuilder.get_object("brake_pedal")

        # test for accerlate, brake, or idle
        if self.car_accelerate == True:
            gas_pedal_image.set_from_file(scriptFolder + "/resources/gas_shoe.png")
        elif self.car_brake == True:
            brake_pedal_image.set_from_file(scriptFolder + "/resources/brake_shoe.png")
        else:
            # idle state
            gas_pedal_image.set_from_file(scriptFolder + "/resources/gas.png")
            brake_pedal_image.set_from_file(scriptFolder + "/resources/brake.png")


    def localApp(self):
        global GladeBuilder

        GladeBuilder.add_from_file(os.path.join(scriptFolder, layoutPath))
        GladeBuilder.connect_signals(self.eventHandler)

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(scriptFolder, "resources/app.css"))
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.MainWindow = GladeBuilder.get_object("mainWindow")
        self.aboutWindow = GladeBuilder.get_object("aboutWindow")

        self.CANdemobutton = GladeBuilder.get_object("CAN_demo_button")
        self.DMSdemobutton = GladeBuilder.get_object("DMS_demo_button")
        self.FITdemobutton = GladeBuilder.get_object("FIT_demo_button")

        self.MainWindow.fullscreen()
        self.MainWindow.show_all()

        Gtk.main()

    class Handler:
        def __init__(self, outer_instance):
            self.outer_instance = outer_instance
            self.image_path = scriptFolder+"/resources/imageseq"
            self.image_files = [os.path.join(self.image_path, f"ezgif-frame-{str(i).zfill(3)}.jpg") for i in range(2, 52)]
            self.current_image_index = 0
            self.images = [GdkPixbuf.Pixbuf.new_from_file(file) for file in self.image_files]
            self.lastDrawTime = datetime.datetime.now()
            self.distance = 0
            self.timePrevious = datetime.datetime.now()

        def on_mainWindow_destroy(self, *args):
            Gtk.main_quit(*args)

        def put_text(self, pixbuf, text, fontsize, r, g, b, x, y):
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixbuf.get_width(), pixbuf.get_height())
            context = cairo.Context(surface)

            Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
            context.paint() #paint the pixbuf

            #add the text
            context.move_to(x, y+fontsize)
            #context.select_font_face('sans-serif')
            font_args=[cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD]
            context.select_font_face('sans-serif', *font_args)
            context.set_font_size(fontsize)
            context.set_source_rgba(r,g,b,1)
            context.show_text(text)
            #get the resulting pixbuf
            surface= context.get_target()
            pixbuf= Gdk.pixbuf_get_from_surface(surface, 0, 0, surface.get_width(), surface.get_height())

            return pixbuf

        def CapImage_event(self, widget, context):
            global globalFrame
            global cameraOpen
            global activeDemo
            global carSpeed

            if (activeDemo == 2):
                # Get the allocated size of the window
                width, height = widget.get_allocated_width(), widget.get_allocated_height()

                # Calculate the position to center the image
                image_width, image_height = self.images[self.current_image_index].get_width(), self.images[self.current_image_index].get_height()

                x = (width - image_width) // 2
                y = (height - image_height) // 2

                nowTime = datetime.datetime.now()
                delta = nowTime - self.timePrevious
                self.distance = self.distance + (carSpeed*(delta.total_seconds()/3600))
                self.timePrevious = nowTime

                tempPixBuff = self.images[self.current_image_index]
                tempPixBuff = self.put_text(tempPixBuff,'Speed', 30, 0.5, 0.5, 0.5, 105, 290)
                tempPixBuff = self.put_text(tempPixBuff,str(carSpeed)+' mph', 30, 1, 1, 1, 105, 322)
                tempPixBuff = self.put_text(tempPixBuff,'Trip', 30, 0.5, 0.5, 0.5, 420, 290)
                tempPixBuff = self.put_text(tempPixBuff,("%4.1f miles" % self.distance), 30, 1, 1, 1, 410, 322)
                Gdk.cairo_set_source_pixbuf(context, tempPixBuff, x, y)

                nowTime = datetime.datetime.now()
                delta = nowTime - self.lastDrawTime

                timeout = (300-(carSpeed*3))

                if(int(delta.microseconds / 1000) > timeout):
                    if (carSpeed > 0):
                        # Increment the image index
                        self.current_image_index = (self.current_image_index + 1) % len(self.images)

                    self.lastDrawTime = nowTime
                context.paint()

            elif cameraOpen:
                frame = globalFrame[:, ::-1, :]
                height, width, _ = frame.shape # 240, 320
                margin_y, margin_x = int(height/4), int(width/4) # 60, 80
                center_y, center_x = int(height/2), int(width/2) # 120, 160
                frame = frame[margin_y:center_y+margin_y, margin_x:center_x+margin_x]
                frame = cv2.cvtColor(frame[:,:,::-1], cv2.COLOR_BGR2RGBA).astype('uint8')
                H, W, C = frame.shape
                surface = cairo.ImageSurface.create_for_data(frame, cairo.FORMAT_ARGB32, W, H)
                CWidth = widget.get_allocation().width
                CHeight = widget.get_allocation().height

                frameScale = CHeight/H
                context.scale(frameScale, frameScale)

                if frameScale > 1:
                    context.set_source_surface(surface, 0, 0)
                else:
                    context.set_source_surface(surface, (W-CWidth)/2, 0)
                context.rotate (pi/2)
                context.paint()
            widget.queue_draw()

        def reset_button_clicked_cb(self, widget):
            self.outer_instance.clickCallback("event_reset")

        def gas_button_pressed_cb(self, widget, event):
            if event.type == Gdk.EventType.BUTTON_PRESS:
                self.outer_instance.car_accelerate = True
                self.outer_instance.car_brake = False
                self.outer_instance.clickCallback("car_accelerate")

        def gas_button_released_cb(self, widget, event):
            if event.type == Gdk.EventType.BUTTON_RELEASE:
                self.outer_instance.car_accelerate = False
                self.outer_instance.car_brake = False
                self.outer_instance.clickCallback("car_idle")

        def brake_button_pressed_cb(self, widget, event):
            if event.type == Gdk.EventType.BUTTON_PRESS:
                self.outer_instance.car_accelerate = False
                self.outer_instance.car_brake = True
                self.outer_instance.clickCallback("car_brake")

        def brake_button_released_cb(self, widget, event):
            if event.type == Gdk.EventType.BUTTON_RELEASE:
                self.outer_instance.car_accelerate = False
                self.outer_instance.car_brake = False
                self.outer_instance.clickCallback("car_idle")

        def on_demo_select_switch_page(self, notebook, page, page_number):
            self.UpdateButtonCSS(page_number)
            self.outer_instance.clickCallback("page"+str(page_number))

        def toggle_DMS_acceleration(self, widget):
            self.outer_instance.clickCallback("toggle_DMS_Acceleration")

        def close_about(self, *args):
            self.outer_instance.aboutWindow.hide()

        def open_about(self, *args):
            self.outer_instance.aboutWindow.set_transient_for(self.outer_instance.MainWindow)
            self.outer_instance.aboutWindow.run()

        def UpdateButtonCSS(self, page_number):
            if page_number == 0:
                self.outer_instance.FITdemobutton.set_name('menu_button_select')
                self.outer_instance.DMSdemobutton.set_name('menu_button')
                self.outer_instance.CANdemobutton.set_name('menu_button')
            elif page_number == 1:
                self.outer_instance.FITdemobutton.set_name('menu_button')
                self.outer_instance.DMSdemobutton.set_name('menu_button_select')
                self.outer_instance.CANdemobutton.set_name('menu_button')
            elif page_number == 2:
                self.outer_instance.FITdemobutton.set_name('menu_button')
                self.outer_instance.DMSdemobutton.set_name('menu_button')
                self.outer_instance.CANdemobutton.set_name('menu_button_select')

