/**
 * Arduino 串口通信示例
 * 功能：接收电脑发送的命令，控制 LED 并返回状态
 */

// 定义引脚
const int LED_PIN = 13;
const int RELAY_PIN = 7;

// 命令缓冲区
String command = "";
bool commandComplete = false;

void setup() {
  // 初始化串口，波特率 115200
  Serial.begin(115200);
  
  // 设置引脚模式
  pinMode(LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  
  // 初始状态
  digitalWrite(LED_PIN, LOW);
  digitalWrite(RELAY_PIN, LOW);
  
  // 发送就绪信息
  Serial.println("Arduino Ready!");
}

void loop() {
  // 检查是否有完整命令
  if (commandComplete) {
    processCommand(command);
    command = "";
    commandComplete = false;
  }
}

// 串口接收事件
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      commandComplete = true;
    } else {
      command += inChar;
    }
  }
}

// 处理命令
void processCommand(String cmd) {
  cmd.trim();  // 去除空白字符
  cmd.toUpperCase();  // 转换为大写
  
  Serial.print("Received: ");
  Serial.println(cmd);
  
  // LED 控制命令
  if (cmd == "LED_ON") {
    digitalWrite(LED_PIN, HIGH);
    Serial.println("OK:LED is ON");
  }
  else if (cmd == "LED_OFF") {
    digitalWrite(LED_PIN, LOW);
    Serial.println("OK:LED is OFF");
  }
  else if (cmd == "LED_STATUS") {
    int state = digitalRead(LED_PIN);
    Serial.print("OK:LED is ");
    Serial.println(state ? "ON" : "OFF");
  }
  // 继电器控制
  else if (cmd == "RELAY_ON") {
    digitalWrite(RELAY_PIN, HIGH);
    Serial.println("OK:Relay is ON");
  }
  else if (cmd == "RELAY_OFF") {
    digitalWrite(RELAY_PIN, LOW);
    Serial.println("OK:Relay is OFF");
  }
  // 传感器读取
  else if (cmd == "READ_TEMP") {
    float temp = readTemperature();
    Serial.print("OK:TEMP=");
    Serial.println(temp);
  }
  else if (cmd == "READ_HUMIDITY") {
    float humi = readHumidity();
    Serial.print("OK:HUMI=");
    Serial.println(humi);
  }
  // 未知命令
  else {
    Serial.print("ERROR:Unknown command: ");
    Serial.println(cmd);
  }
}

// 模拟读取温度
float readTemperature() {
  // 实际项目中替换为真实传感器读取
  return 25.5;
}

// 模拟读取湿度
float readHumidity() {
  // 实际项目中替换为真实传感器读取
  return 60.0;
}
