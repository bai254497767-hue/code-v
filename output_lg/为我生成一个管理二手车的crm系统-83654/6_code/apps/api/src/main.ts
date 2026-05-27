import { ValidationPipe } from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule);
  const config = app.get(ConfigService);

  app.setGlobalPrefix(config.get<string>("API_PREFIX", "api/v1"));
  app.enableCors({
    origin: config.get<string>("CORS_ORIGIN", "http://localhost:3000"),
    credentials: true
  });
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true
    })
  );

  const port = config.get<number>("API_PORT", 3001);
  await app.listen(port);
}

void bootstrap();
