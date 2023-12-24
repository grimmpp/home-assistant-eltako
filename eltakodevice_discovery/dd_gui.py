import sys
import os
from os.path import expanduser
import glob
import serial
from typing import Final
import logging
import asyncio

import termcolor

import tkinter as tk
from tkinter import ttk, filedialog
from threading import *
import tkinter as tk
import tkinter.scrolledtext as ScrolledText

import ha_discovery


class BaseThread(Thread):
    def __init__(self, callback=None, callback_args=None, *args, **kwargs):
        target = kwargs.pop('target')
        super(BaseThread, self).__init__(target=self.target_with_callback, *args, **kwargs)
        self.callback = callback
        self.method = target
        self.callback_args = callback_args

    def target_with_callback(self, *args, **kwargs):
        self.method(*args)
        if self.callback is not None:
            self.callback(*self.callback_args)


class TextHandler(logging.Handler):
    """This class allows you to log to a Tkinter Text or ScrolledText widget"""

    def __init__(self, text_box:tk.Text):
        # run the regular Handler __init__
        logging.Handler.__init__(self)
        # Store a reference to the Text it will log to
        self.text_box = text_box

    def emit(self, record):
        msg = self.format(record)
        color_name = None
        start_pos = 0
        end_pos = 0
        if '\033[' in msg:
            start_pos = msg.find('\033[')
            color_code = msg[start_pos+2:start_pos+4]
            colors = list([k for k, v in termcolor.COLORS.items() if str(v) == color_code])
            if len(colors) > 0:
                color_name = colors[0]
            end_pos = msg.find(termcolor.RESET)
            msg = msg[0:start_pos] + msg[start_pos+5:]
            msg = msg[0:end_pos-5] + msg[end_pos:]
            end_pos = end_pos-5

        def append():
            self.text_box.configure(state='normal')
            self.text_box.insert(tk.END, msg + '\n')
            self.text_box.configure(state='disabled')
            if color_name:
                final_index = str(self.text_box.index(tk.END))
                num_of_lines = int(final_index.split('.')[0])-2

                # self.text_box.tag_config('mark', foreground=color_name)
                # self.text_box.tag_add('mark', f"{num_of_lines}.{start_pos}", f"{num_of_lines}.{end_pos}")
            # Autoscroll to the bottom
            self.text_box.yview(tk.END)
        # This is necessary because we can't modify the Text from other threads
        self.text_box.after(0, append)



def get_serial_ports() -> [str]:
    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

def refresh_serial_paths(combobox:ttk.Combobox):
    combobox['values'] = get_serial_ports()
    logging.info(termcolor.colored("test ist ein test", 'red'))

def get_base_address_range() -> [str]:
    result = []
    for i in range(0,16):
        result.append(f"B{str(hex(i)).replace('0x','').upper()}")
    return result

DEFAULT_FILENAME: Final = 'ha_eltako_configuration.yaml'
def save_file(label_fn: tk.Label):
    f = filedialog.asksaveasfile(initialfile = DEFAULT_FILENAME, 
                                 title="Save Configuration File",
                                 initialdir= expanduser("~"),
                                 defaultextension=".yaml",filetypes=[("All Files","*.*"),("YAML","*.yaml")])
    label_fn.config(text = f.name)


def run_main(btns: [tk.Button], serial_port:str, base_address:str, filename:str):
    for b in btns: 
        b['state'] = 'disable'
    
    def on_done():
        for b in btns: 
            b['state'] = 'normal'

    t1=BaseThread(
        target=ha_discovery.run, args=(1, serial_port, 57600, f"0x0000{base_address}00", False, filename),
        callback=on_done, callback_args=[])
    t1.start()


window = tk.Tk()
window.title("Home Assistant Config Generator")

# description
frame = tk.Frame(master=window, padx="5", pady="5")
frame.pack(anchor='w')
label_sp = tk.Label(master=frame, text="Description")
label_sp.pack(side=tk.TOP, anchor='w')

# serial port
frame = tk.Frame(master=window, padx="5", pady="5")
frame.pack(anchor='w')

label_sp = tk.Label(master=frame, text="Serial Port:")
label_sp.pack(side=tk.LEFT)

combobox_sp = ttk.Combobox(frame, state="readonly", width="75", values=get_serial_ports()) 
combobox_sp.set(get_serial_ports()[0])
combobox_sp.pack(side=tk.LEFT)

btn_refresh_sp = tk.Button(master=frame, text="scan serial ports", command=lambda:refresh_serial_paths(combobox_sp)  )
btn_refresh_sp.pack(side=tk.LEFT)

# base address
frame = tk.Frame(master=window, padx="5", pady="5")
frame.pack(anchor='w')

label_ba = tk.Label(master=frame, text="Base Address")
label_ba.pack(side=tk.LEFT)

label_ba_fp = tk.Label(master=frame, text="00-00-")
label_ba_fp.pack(side=tk.LEFT)
combobox_ba = ttk.Combobox(frame, state="readonly", width="3", values=get_base_address_range()) 
combobox_ba.set(get_base_address_range()[0])
combobox_ba.pack(side=tk.LEFT)
label_ba_lp = tk.Label(master=frame, text="-00")
label_ba_lp.pack(side=tk.LEFT)

# store file
frame = tk.Frame(master=window, padx="5", pady="5")
frame.pack(anchor='w')
label_fn_l = tk.Label(master=frame, text="Filename: ")
label_fn_l.pack(side=tk.LEFT)

label_fn = tk.Label(master=frame, text=os.path.join(expanduser("~"), DEFAULT_FILENAME) )

btn_fn_dialog = tk.Button(master=frame, text="Choose Filename", command= lambda:save_file(label_fn))
btn_fn_dialog.pack(side=tk.LEFT)

label_fn.pack(side=tk.LEFT)

# Run button
frame = tk.Frame(master=window, padx="5", pady="5")
frame.pack(anchor='w')

btn_run = tk.Button(master=frame, text="=> RUN <=")
btn_run['command'] = lambda:run_main([btn_run, btn_refresh_sp, btn_fn_dialog], combobox_sp.get(), combobox_ba.get(), label_fn['text'])
# btn_run["state"] = "disabled"
btn_run.pack(side=tk.LEFT)

# Create textLogger
st = ScrolledText.ScrolledText(window, state='disabled', background='black', foreground='lightgrey')
st.configure(font='TkFixedFont')
st.pack(anchor='w')
# log_box_1 = tk.Text(window, borderwidth=3, relief="sunken")
# log_box_1.pack(anchor='w')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler( TextHandler(st) )



window.mainloop()