# 선박 플랫폼 연동 API 기술 명세서

> 이 문서는 C2 플랫폼으로부터 데이터를 수신하는 **선박 플랫폼(Ship Platform)** 개발자를 위한 상세 기술 명세입니다.

---

## 목차

1. [연동 구조 개요](#1-연동-구조-개요)
2. [공통 규격](#2-공통-규격)
3. [API 1 — 위치 제공 `GET /api/position`](#3-api-1--위치-제공-get-apiposition)
4. [API 2 — 경로 수신 `POST /api/route`](#4-api-2--경로-수신-post-apiroute)
5. [RTZ XML 상세 구조](#5-rtz-xml-상세-구조)
6. [구현 예시 (NestJS)](#6-구현-예시-nestjs)
7. [테스트 방법](#7-테스트-방법)

---

## 1. 연동 구조 개요

```
[C2 플랫폼]                         [선박 플랫폼]
    │                                     │
    │── GET /api/position ──────────────► │  (매 5초, 위경도 폴링)
    │◄─ { lat, lon, heading } ──────────  │
    │                                     │
    │── POST /api/route ────────────────► │  (RTZ 파일 전송 시)
    │   Body: RTZ XML                     │  ← 이 문서에서 설명
    │◄─ { success: true } ─────────────  │
```

C2 플랫폼은 선박 등록 시 입력한 `platform_url`을 기준으로 위 두 엔드포인트를 호출합니다.

**예시:** `platform_url = http://192.168.1.100:4000`
- 위치 폴링: `GET http://192.168.1.100:4000/api/position`
- 경로 전송: `POST http://192.168.1.100:4000/api/route`

---

## 2. 공통 규격

| 항목 | 내용 |
|---|---|
| 프로토콜 | HTTP/1.1 |
| 인코딩 | UTF-8 |
| 공통 요청 헤더 | `x-app-lang: en` |
| 인증 | 없음 (내부망 전용) |

> **중요:** C2 플랫폼은 모든 요청에 `x-app-lang: en` 헤더를 포함합니다.
> 선박 플랫폼 미들웨어에서 이 헤더를 필수로 검증하는 경우 반드시 허용해야 합니다.

---

## 3. API 1 — 위치 제공 `GET /api/position`

C2 플랫폼이 **5초마다 자동으로 호출**합니다. 응답 값으로 C2 지도 위의 선박 위치를 갱신합니다.

### 요청 (C2 → 선박 플랫폼)

```
GET /api/position HTTP/1.1
Host: 192.168.1.100:4000
x-app-lang: en
```

### 응답 (선박 플랫폼 → C2)

**성공 시 (HTTP 200)**

```json
{
  "success": true,
  "data": {
    "lat": 25.77,
    "lon": -80.12,
    "heading": 45.0
  }
}
```

또는 flat 구조도 허용합니다:

```json
{
  "lat": 25.77,
  "lon": -80.12,
  "heading": 45.0
}
```

**응답 필드 설명**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `lat` | float | ✅ | 위도 (WGS84 기준, -90.0 ~ 90.0) |
| `lon` | float | ✅ | 경도 (WGS84 기준, -180.0 ~ 180.0) |
| `heading` | float | ❌ | 선수 방위각 (진북 기준 0~360°, 없으면 이전 값 유지) |

**실패 시 (HTTP 200 이외)**

HTTP 상태 코드가 200이 아니면 C2 지도에서 해당 선박이 `disconnected(끊김)` 상태로 표시됩니다.

---

## 4. API 2 — 경로 수신 `POST /api/route`

C2 웹 UI에서 **"📡 전송" 버튼**을 클릭할 때 호출됩니다.
RTZ 형식의 XML 원문을 body로 전달합니다.

### 요청 (C2 → 선박 플랫폼)

```
POST /api/route HTTP/1.1
Host: 192.168.1.100:4000
Content-Type: application/xml
x-app-lang: en
Content-Length: <바이트 수>

<?xml version='1.0' encoding='UTF-8'?>
<route xmlns="http://www.cirm.org/RTZ/1/0" version="1.0">
  ... (RTZ XML 전체, 아래 섹션 참고)
</route>
```

### 응답 (선박 플랫폼 → C2)

**성공 시 (HTTP 200 또는 201)**

```json
{
  "success": true
}
```

HTTP 상태 코드 200~399 범위이면 C2에서 전송 성공으로 기록합니다.

**실패 시 (HTTP 400 이상)**

C2 UI에 전송 실패 및 에러 메시지가 표시됩니다.

---

## 5. RTZ XML 상세 구조

body로 전달되는 RTZ XML의 전체 구조와 각 필드 설명입니다.

### 실제 전송 예시 (rtz_sample.xml)

```xml
<?xml version='1.0' encoding='UTF-8'?>
<route xmlns="http://www.cirm.org/RTZ/1/0" version="1.0">

  <!-- ① 경로 메타데이터 -->
  <routeInfo routeName="Miami Demo Route" routeAuthor="Author" />

  <!-- ② 웨이포인트 목록 -->
  <waypoints>

    <!-- WP 0 : 출발점 (extensions 없음 = 기본 통과 포인트) -->
    <waypoint id="0">
      <position lat="25.77" lon="-80.12" />
    </waypoint>

    <!-- WP 1 : 항법 데이터 포함 -->
    <waypoint id="1">
      <position lat="25.80" lon="-80.08" />
      <extensions>
        <extension name="WaypointExtension(example)" manufacturer="Vendor">
          <waypointType type="TaskPoint" />
          <missionData
            desiredCourse="40.0"
            desiredSpeed="12.0"
            starboardXTD="0.5"
            portXTD="0.5"
            geometryType="Loxodrome" />
        </extension>
      </extensions>
    </waypoint>

    <!-- WP 2 : 복수 missionData 가능 -->
    <waypoint id="2">
      <position lat="25.90" lon="-80.10" />
      <extensions>
        <extension name="WaypointExtension(example)" manufacturer="Vendor">
          <waypointType type="MissionWaypoint" />
          <missionData
            description="North patrol"
            passWithinRadius="0.3"
            desiredSpeed="10.0"
            geometryType="Loxodrome"
            starboardXTD="0.5"
            portXTD="0.5" />
        </extension>
      </extensions>
    </waypoint>

  </waypoints>

  <!-- ③ Keep-In / Keep-Out 구역 -->
  <extensions>
    <extension name="KeepInAndOutArea" manufacturer="Vendor">

      <!-- 진입 유지 구역 : 이 폴리곤 내부에 있어야 함 -->
      <keepInArea>
        <point lat="25.60" lon="-80.35" />
        <point lat="25.60" lon="-79.90" />
        <point lat="26.00" lon="-79.90" />
        <point lat="26.00" lon="-80.35" />
      </keepInArea>

      <!-- 진입 금지 구역 : 이 폴리곤 내부에 들어가면 안 됨 -->
      <keepOutArea>
        <point lat="25.74" lon="-80.18" />
        <point lat="25.74" lon="-80.13" />
        <point lat="25.78" lon="-80.13" />
        <point lat="25.78" lon="-80.18" />
      </keepOutArea>

    </extension>
  </extensions>

</route>
```

---

### 필드별 상세 설명

#### ① routeInfo

| 속성 | 타입 | 설명 |
|---|---|---|
| `routeName` | string | 경로 이름 (표시용) |
| `routeAuthor` | string | 작성자 (표시용) |

---

#### ② waypoint

| 요소/속성 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `waypoint[id]` | int | ✅ | WP 순번 (0부터 시작, 이 순서대로 항해) |
| `position[lat]` | float | ✅ | WP 위도 (WGS84) |
| `position[lon]` | float | ✅ | WP 경도 (WGS84) |

**extension 내부 선택 필드**

| 요소/속성 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `waypointType[type]` | string | ❌ | WP 역할 (`TaskPoint`, `MissionWaypoint` 등 자유 정의) |
| `missionData[desiredCourse]` | float | ❌ | 목표 침로 (진북 기준 도°) |
| `missionData[desiredSpeed]` | float | ❌ | 목표 속력 (knots) |
| `missionData[starboardXTD]` | float | ❌ | 우현 허용 이탈 폭 (해리, NM) |
| `missionData[portXTD]` | float | ❌ | 좌현 허용 이탈 폭 (해리, NM) |
| `missionData[passWithinRadius]` | float | ❌ | 이 반경 내 통과 기준 (해리, NM) |
| `missionData[geometryType]` | string | ❌ | 항법 기하학 (`Loxodrome`=등각항법, `GreatCircle`=대권항법) |
| `missionData[description]` | string | ❌ | 임무 설명 (자유 텍스트) |

---

#### ③ keepInArea / keepOutArea

폴리곤 꼭짓점을 `<point>` 요소로 순서대로 나열합니다.
마지막 점과 첫 번째 점을 연결하면 닫힌 폴리곤이 됩니다.

| 요소 | 설명 |
|---|---|
| `keepInArea` | **진입 유지 구역.** 선박은 이 폴리곤 내부에 있어야 합니다. |
| `keepOutArea` | **진입 금지 구역.** 선박은 이 폴리곤 내부에 들어가면 안 됩니다. |
| `point[lat]` | 꼭짓점 위도 |
| `point[lon]` | 꼭짓점 경도 |

> `keepInArea`와 `keepOutArea`는 각각 0개 이상 존재할 수 있습니다.

---

## 6. 구현 예시 (NestJS)

### RTZ XML 파싱 유틸리티

```typescript
import { XMLParser } from 'fast-xml-parser';

const RTZ_NS = 'http://www.cirm.org/RTZ/1/0';

export interface RtzWaypoint {
  id: number;
  lat: number;
  lon: number;
  desiredCourse?: number;
  desiredSpeed?: number;
  waypointType?: string;
}

export interface RtzZone {
  points: { lat: number; lon: number }[];
}

export interface ParsedRoute {
  routeName: string;
  waypoints: RtzWaypoint[];
  keepInAreas: RtzZone[];
  keepOutAreas: RtzZone[];
}

export function parseRtz(xmlBody: string): ParsedRoute {
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_' });
  const doc = parser.parse(xmlBody);
  const route = doc['route'];

  // 경로 이름
  const routeName = route?.routeInfo?.['@_routeName'] ?? '';

  // 웨이포인트
  const rawWps = route?.waypoints?.waypoint ?? [];
  const wpArray = Array.isArray(rawWps) ? rawWps : [rawWps];
  const waypoints: RtzWaypoint[] = wpArray.map((wp: any) => {
    const ext = wp?.extensions?.extension;
    const mission = ext?.missionData ?? {};
    return {
      id: Number(wp['@_id']),
      lat: Number(wp.position['@_lat']),
      lon: Number(wp.position['@_lon']),
      desiredCourse: mission['@_desiredCourse'] != null ? Number(mission['@_desiredCourse']) : undefined,
      desiredSpeed: mission['@_desiredSpeed'] != null ? Number(mission['@_desiredSpeed']) : undefined,
      waypointType: ext?.waypointType?.['@_type'],
    };
  });

  // Keep-In / Keep-Out 구역
  const zoneExt = route?.extensions?.extension;
  const parseZone = (raw: any): RtzZone => {
    const pts = Array.isArray(raw?.point) ? raw.point : raw?.point ? [raw.point] : [];
    return { points: pts.map((p: any) => ({ lat: Number(p['@_lat']), lon: Number(p['@_lon']) })) };
  };

  const keepInAreas: RtzZone[] = zoneExt?.keepInArea ? [parseZone(zoneExt.keepInArea)] : [];
  const keepOutAreas: RtzZone[] = zoneExt?.keepOutArea ? [parseZone(zoneExt.keepOutArea)] : [];

  return { routeName, waypoints, keepInAreas, keepOutAreas };
}
```

### 컨트롤러

```typescript
import { Controller, Post, Body, Req, Res, HttpCode } from '@nestjs/common';
import { Request, Response } from 'express';
import { parseRtz } from './rtz.util';

@Controller('api')
export class RouteController {

  @Post('route')
  @HttpCode(200)
  async receiveRoute(@Req() req: Request, @Res() res: Response) {
    // raw XML body 읽기 (NestJS에서 raw body 미들웨어 필요)
    const xmlBody: string = req.body.toString('utf-8');

    try {
      const route = parseRtz(xmlBody);

      console.log('경로 수신:', route.routeName);
      console.log('웨이포인트 수:', route.waypoints.length);
      console.log('Keep-In 구역 수:', route.keepInAreas.length);
      console.log('Keep-Out 구역 수:', route.keepOutAreas.length);

      // TODO: 여기서 자체 지도/콘솔에 경로 렌더링
      // this.mapService.drawRoute(route);

      return res.json({ success: true });
    } catch (err) {
      return res.status(400).json({ success: false, message: 'RTZ 파싱 실패', error: err.message });
    }
  }
}
```

### main.ts — raw body 미들웨어 설정

NestJS에서 `application/xml` body를 raw Buffer로 읽으려면 아래 설정이 필요합니다.

```typescript
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import * as bodyParser from 'body-parser';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bodyParser: false });

  // JSON은 기본 파서 사용
  app.use(bodyParser.json());

  // application/xml은 raw Buffer로 수신
  app.use(bodyParser.raw({ type: 'application/xml', limit: '10mb' }));

  await app.listen(4000);
}
bootstrap();
```

---

## 7. 테스트 방법

### 위치 API 테스트

```bash
curl -X GET http://localhost:4000/api/position \
  -H "x-app-lang: en"
```

예상 응답:
```json
{"success":true,"data":{"lat":25.77,"lon":-80.12,"heading":45.0}}
```

---

### 경로 수신 API 테스트

`rtz_sample.xml` 파일을 직접 전송합니다:

```bash
curl -X POST http://localhost:4000/api/route \
  -H "Content-Type: application/xml" \
  -H "x-app-lang: en" \
  --data-binary @rtz_sample.xml
```

예상 응답:
```json
{"success":true}
```

---

### 파싱 결과 예시

위 `rtz_sample.xml`을 파싱하면 다음 구조를 얻게 됩니다:

```json
{
  "routeName": "Miami Demo Route",
  "waypoints": [
    { "id": 0, "lat": 25.77, "lon": -80.12 },
    { "id": 1, "lat": 25.80, "lon": -80.08, "desiredCourse": 40.0, "desiredSpeed": 12.0, "waypointType": "TaskPoint" },
    { "id": 2, "lat": 25.90, "lon": -80.10, "desiredSpeed": 10.0, "waypointType": "MissionWaypoint" }
  ],
  "keepInAreas": [
    {
      "points": [
        { "lat": 25.60, "lon": -80.35 },
        { "lat": 25.60, "lon": -79.90 },
        { "lat": 26.00, "lon": -79.90 },
        { "lat": 26.00, "lon": -80.35 }
      ]
    }
  ],
  "keepOutAreas": [
    {
      "points": [
        { "lat": 25.74, "lon": -80.18 },
        { "lat": 25.74, "lon": -80.13 },
        { "lat": 25.78, "lon": -80.13 },
        { "lat": 25.78, "lon": -80.18 }
      ]
    }
  ]
}
```

---

## 구현 체크리스트

- [ ] `GET /api/position` 구현 — lat/lon/heading 반환
- [ ] `POST /api/route` 구현 — `application/xml` body 수신
- [ ] `x-app-lang: en` 헤더 허용
- [ ] RTZ XML 파싱 — 웨이포인트 순서대로 추출
- [ ] RTZ XML 파싱 — keepInArea 폴리곤 추출
- [ ] RTZ XML 파싱 — keepOutArea 폴리곤 추출
- [ ] 자체 콘솔/지도에 경로 렌더링
