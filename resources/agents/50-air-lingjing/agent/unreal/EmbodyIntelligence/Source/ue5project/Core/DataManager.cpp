// Fill out your copyright notice in the Description page of Project Settings.


#include "DataManager.h"

#include "CesiumGeoreference.h"
#include "GamePlayManager.h"
#include "ue5project/Core/LDataStruct.h"
#include "ue5project/Interaction/UserInterface/MainWidgetController.h"
#include "ue5project/Net/MessageHelper/PhotoRequest/LPhotoRequestStruct.h"
#include "ue5project/Net/UdpHelper/LUdpServer.h"
#include "ue5project/Net/WebSocketHelper/LWebSocketClient.h"
#include "ue5project/Scene/Equipment/EquipmentActor.h"
#include "ue5project/Scene/Equipment/ShipActor.h"
#include "ue5project/Scene/Equipment/EquipmentStruct.h"
#include "ue5project/Scene/Equipment/FEquipmentController.h"
#include "ue5project/Scene/Task/TaskStruct.h"
#include "ue5project/Scene/Task/TaskMatrixController.h"
#include "ue5project/Temp/BlueprintTempHelper.h"

#define WEBSOCKET_URL TEXT("ws://127.0.0.1:9909/ws/LJ-ENGINE/image")

FString ADataManager::GetTaskId() const
{
	return TaskId;
}

void ADataManager::BeginPlay()
{
	Super::BeginPlay();
	UE_LOG(LogTemp, Log, TEXT("ADataManager: BeginPlay - binding UDP server(8802) and WebSocket"));

	FLUdpServer::Get()->OnDataReceived().BindUObject(this, &ADataManager::OnUdpReceiveMessage);
	FLUdpServer::Get()->Start("" ,8802);

	FLWebSocketClient::Get()->OnMessage().BindUObject(this, &ADataManager::OnWebSocketReceivedMessage);
	FLWebSocketClient::Get()->OnConnectionError().BindUObject(this, &ADataManager::OnWebSocketConnectionError);
	FLWebSocketClient::Get()->OnClosed().BindUObject(this, &ADataManager::OnWebSocketClosed);
	FLWebSocketClient::Get()->Connect(WEBSOCKET_URL);

	FGamePlayManager::Get()->WorldContext = GetWorld();
	FEquipmentController::Get()->ClearEquipments();
	FTaskMatrixController::Get()->ClearTaskPoints();
	
	FTempController::Get()->DataManager = this;

}

void ADataManager::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	UE_LOG(LogTemp, Log, TEXT("ADataManager: EndPlay - stopping UDP/WebSocket"));
	FLUdpServer::Get()->Stop();
	FLWebSocketClient::Get()->Close();

	FEquipmentController::Get()->ClearEquipments();
	FTaskMatrixController::Get()->ClearTaskPoints();

	Super::EndPlay(EndPlayReason);
}

void ADataManager::OnUdpReceiveMessage(const FString& InMessage, const FString& InSenderEndPoint)
{
	TSharedPtr<FJsonObject> JsonObject;
	if (const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
		!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
			FString::Printf(TEXT("ADataManager: Deserialize Message Failed: %s"), *InMessage));
		return;
	}

	// data
	for (const TArray<TSharedPtr<FJsonValue>>& DataJsonList = JsonObject->GetArrayField(TEXT("data"));
		 const TSharedPtr<FJsonValue>& DataJsonValue : DataJsonList)
	{
		const TSharedPtr<FJsonObject> DataJsonObject = DataJsonValue->AsObject();
		if (!DataJsonObject.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: UDP 'data' element is not an object, skipped"));
			continue;
		}

		FString DataType;
		JsonObject->TryGetStringField(TEXT("type"), DataType);
		if (DataType == TEXT("DATA"))
		{
			OnReceiveUdpDataMessage(DataJsonObject);
		}
		else if (DataType == TEXT("EVENT"))
		{
			OnReceiveUdpEventMessage(DataJsonObject);
		}
		else
		{
			GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow, 
				FString::Printf(TEXT("ADataManager: Invalid Udp Message Type, Type: %s"), *DataType));
		}
	}
}

void ADataManager::OnReceiveUdpDataMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveUdpDataMessage - invalid json object"));
		return;
	}

	// equipmentType may be string (drone/car/dog) or integer (0=satellite, 2=ship)
	FString EquipmentTypeStr;
	int32 EquipmentTypeNum = -1;
	InJsonObject->TryGetStringField(TEXT("equipmentType"), EquipmentTypeStr);
	InJsonObject->TryGetNumberField(TEXT("equipmentType"), EquipmentTypeNum);

	if (EquipmentTypeStr == TEXT("drone"))
	{
		OnReceiveDroneMessage(InJsonObject);
	}
	else if (EquipmentTypeStr == TEXT("car"))
	{
		OnReceiveCarMessage(InJsonObject);
	}
	else if (EquipmentTypeStr == TEXT("dog"))
	{
		OnReceiveDogMessage(InJsonObject);
	}
	else if (EquipmentTypeNum == 2)
	{
		OnReceiveShipMessage(InJsonObject);
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: Unknown equipmentType (str='%s', num=%d)"), *EquipmentTypeStr, EquipmentTypeNum);
	}
}

void ADataManager::OnReceiveUdpEventMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveUdpEventMessage - invalid json object"));
		return;
	}

	// get eventType string
	FString EquipmentTypeStr;
	InJsonObject->TryGetStringField(TEXT("eventType"), EquipmentTypeStr);

	if (EquipmentTypeStr == TEXT("removeTaskPoint"))
	{
		FString TaskPointId;
		InJsonObject->TryGetStringField(TEXT("taskPointId"), TaskPointId);
		FTaskMatrixController::Get()->RemoveTaskPoint(TaskPointId);
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: Unknown eventType '%s'"), *EquipmentTypeStr);
	}
}

void ADataManager::OnReceiveDroneMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveDroneMessage - invalid json object"));
		return;
	}

	FDroneData DroneData;
	InJsonObject->TryGetStringField(TEXT("droneID"), DroneData.DroneId);
	InJsonObject->TryGetNumberField(TEXT("x"), DroneData.Location.X);
	InJsonObject->TryGetNumberField(TEXT("y"), DroneData.Location.Y);
	InJsonObject->TryGetNumberField(TEXT("z"), DroneData.Location.Z);
	InJsonObject->TryGetNumberField(TEXT("pitch"), DroneData.Rotation.Pitch);
	InJsonObject->TryGetNumberField(TEXT("yaw"), DroneData.Rotation.Yaw);
	InJsonObject->TryGetNumberField(TEXT("roll"), DroneData.Rotation.Roll);

	if (AEquipmentActor* Drone = FEquipmentController::Get()->GetEquipment(DroneData.DroneId))
	{
		const FTransform Transform(DroneData.Rotation, DroneData.Location, Drone->GetActorScale3D());
		Drone->UpdateDroneTransform(Transform);
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Drone not found: %s"), *DroneData.DroneId);
	}
}

void ADataManager::OnReceiveCarMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveCarMessage - invalid json object"));
		return;
	}

	FCarData CarData;
	InJsonObject->TryGetStringField(TEXT("car_id"), CarData.CarId);
	InJsonObject->TryGetNumberField(TEXT("x"), CarData.X);
	InJsonObject->TryGetNumberField(TEXT("y"), CarData.Y);
	InJsonObject->TryGetNumberField(TEXT("caryaw"), CarData.CarYaw);
	InJsonObject->TryGetNumberField(TEXT("fl_angle"), CarData.FLAngle);
	InJsonObject->TryGetNumberField(TEXT("fr_angle"), CarData.FRAngle);
	InJsonObject->TryGetBoolField(TEXT("is_alive"), CarData.bIsAlive);
	InJsonObject->TryGetStringField(TEXT("status"), CarData.Status);

	if (AEquipmentActor* Car = FEquipmentController::Get()->GetEquipment(CarData.CarId))
	{
		const FVector&& CarLocation = Car->GetActorLocation();
		const FVector Location(CarData.X, CarData.Y, CarLocation.Z);
		const FVector&& TargetLocation = Car->TraceLocation(Location);
		const FRotator&& CarRotation = Car->GetActorRotation();
		const FRotator Rotation(CarRotation.Pitch, CarData.CarYaw, CarRotation.Roll);
		const FVector&& CarScale = Car->GetActorScale3D();

		const FTransform Transform(Rotation, TargetLocation, CarScale);
		Car->UpdateCarTransform(Transform);
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Car not found: %s"), *CarData.CarId);
	}
}

void ADataManager::OnReceiveDogMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveDogMessage - invalid json object"));
		return;
	}

	FString DogId;
	FVector Location = FVector::ZeroVector;
	double Yaw;
	InJsonObject->TryGetStringField(TEXT("ID"), DogId);
	InJsonObject->TryGetNumberField(TEXT("ue_x"), Location.X);
	InJsonObject->TryGetNumberField(TEXT("ue_y"), Location.Y);
	InJsonObject->TryGetNumberField(TEXT("ue_z"), Location.Z);
	InJsonObject->TryGetNumberField(TEXT("yaw"), Yaw);

	FDogJoint DogJoint;
	const TSharedPtr<FJsonObject> JointsObj = InJsonObject->GetObjectField(TEXT("joints"));
	if (JointsObj.IsValid())
	{
		JointsObj->TryGetNumberField(TEXT("FR_hip"), DogJoint.FRHip);
		JointsObj->TryGetNumberField(TEXT("FR_thigh"), DogJoint.FRThigh);
		JointsObj->TryGetNumberField(TEXT("FR_calf"), DogJoint.FRCalf);
		JointsObj->TryGetNumberField(TEXT("FL_hip"), DogJoint.FLHip);
		JointsObj->TryGetNumberField(TEXT("FL_thigh"), DogJoint.FLThigh);
		JointsObj->TryGetNumberField(TEXT("FL_calf"), DogJoint.FLCalf);
		JointsObj->TryGetNumberField(TEXT("RR_hip"), DogJoint.RRHip);
		JointsObj->TryGetNumberField(TEXT("RR_thigh"), DogJoint.RRThigh);
		JointsObj->TryGetNumberField(TEXT("RR_calf"), DogJoint.RRCalf);
		JointsObj->TryGetNumberField(TEXT("RL_hip"), DogJoint.RLHip);
		JointsObj->TryGetNumberField(TEXT("RL_thigh"), DogJoint.RLThigh);
		JointsObj->TryGetNumberField(TEXT("RL_calf"), DogJoint.RLCalf);
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Dog message missing 'joints' (dog=%s)"), *DogId);
	}

	if (AEquipmentActor* Dog = FEquipmentController::Get()->GetEquipment(DogId))
	{
		const FRotator&& DogRotation = Dog->GetActorRotation();
		const FVector&& DogScale = Dog->GetActorScale3D();
		const FRotator Rotation(DogRotation.Pitch, Yaw, DogRotation.Roll);
		const FVector&& TargetLocation = Dog->TraceLocation(Location);

		const FTransform Transform(Rotation, TargetLocation, DogScale);
		Dog->UpdateDogTransform(Transform, DogJoint);
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Dog not found: %s"), *DogId);
	}
}

void ADataManager::OnReceiveShipMessage(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveShipMessage - invalid json object"));
		return;
	}

	FShipData ShipData;

	// header
	const TSharedPtr<FJsonObject> HeaderObj = InJsonObject->GetObjectField(TEXT("header"));
	if (!HeaderObj.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: Ship message missing 'header'"));
		return;
	}
	HeaderObj->TryGetStringField(TEXT("equipmentId"), ShipData.ShipId);
	HeaderObj->TryGetNumberField(TEXT("dataType"), ShipData.DataType);
	HeaderObj->TryGetNumberField(TEXT("TaskTime"), ShipData.TaskTime);
	HeaderObj->TryGetNumberField(TEXT("step"), ShipData.Step);

	// equipmentInfo -> lonLatAlt
	const TSharedPtr<FJsonObject> EquipmentInfoObj = InJsonObject->GetObjectField(TEXT("equipmentInfo"));
	if (EquipmentInfoObj.IsValid())
	{
		const TArray<TSharedPtr<FJsonValue>>& LonLatAltArray = EquipmentInfoObj->GetArrayField(TEXT("lonLatAlt"));
		if (LonLatAltArray.Num() >= 3
			&& LonLatAltArray[0].IsValid() && LonLatAltArray[1].IsValid() && LonLatAltArray[2].IsValid())
		{
			FVector LonLatAlt;
			LonLatAlt.X = LonLatAltArray[0]->AsNumber();
			LonLatAlt.Y = LonLatAltArray[1]->AsNumber();
			LonLatAlt.Z = LonLatAltArray[2]->AsNumber();

			if (const ACesiumGeoreference* CesiumGeoreference = ACesiumGeoreference::GetDefaultGeoreference(FGamePlayManager::Get()->WorldContext.Get()))
			{
				ShipData.Location = CesiumGeoreference->TransformLongitudeLatitudeHeightPositionToUnreal(LonLatAlt);
			}
			else
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: CesiumGeoreference not available (ship=%s)"), *ShipData.ShipId);
			}
		}
		else
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Ship 'lonLatAlt' invalid (ship=%s)"), *ShipData.ShipId);
		}
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Ship message missing 'equipmentInfo' (ship=%s)"), *ShipData.ShipId);
	}



}

void ADataManager::OnWebSocketReceivedMessage(const FString& InMessage)
{
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
	if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
			FString::Printf(TEXT("ADataManager: Deserialize WebSocket Message Failed: %s"), *InMessage));
		return;
	}

	const TSharedPtr<FJsonObject> DataJsonObject = JsonObject->GetObjectField(TEXT("data"));
	if (!DataJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: WebSocket message missing 'data' field"));
		return;
	}

	FString CommandType;
	DataJsonObject->TryGetStringField(TEXT("commandType"), CommandType);
	if (CommandType == TEXT("resetScenario"))
	{
		OnReceiveScenario(DataJsonObject);
	}
	else if (CommandType == TEXT("takePhoto"))
	{
		OnReceiveTakePhotoTask(DataJsonObject);
	}
	else if (CommandType == TEXT("equipmentMoveTask2D"))
	{
		OnReceiveEquipmentMoveTask2D(DataJsonObject);
	}
	else if (CommandType == TEXT("complete"))
	{
		ResetScene();
	}
	else
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Red, FString::Printf(TEXT("DataManager: Unknown Command Type: %s"), *CommandType));
	}
}

void ADataManager::OnReceiveScenario(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveScenario - invalid json object"));
		return;
	}

	FString _TaskId;
	InJsonObject->TryGetStringField(TEXT("taskId"), _TaskId);
	if (!TaskId.IsEmpty() && _TaskId == TaskId)
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow, FString::Printf(TEXT("DataManager: Duplicate TaskId: %s"), *TaskId));
		return;
	}
	TaskId = _TaskId;

	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Green, FString::Printf(TEXT("DataManager: Scenario Received")));
	UE_LOG(LogTemp, Log, TEXT("ADataManager: Scenario received (taskId=%s)"), *TaskId);

	const TSharedPtr<FJsonObject> ScenarioObject = InJsonObject->GetObjectField(TEXT("scenario"));
	if (!ScenarioObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: Scenario missing 'scenario' field"));
		return;
	}
	const TSharedPtr<FJsonObject> EquipmentObject = ScenarioObject->GetObjectField(TEXT("equipmentList"));
	if (EquipmentObject.IsValid())
	{
		ParseScenarioEquipments(EquipmentObject);
	}
	else
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Scenario missing 'equipmentList'"));
	}

	// taskMatrix can be an object or an array
	const TSharedPtr<FJsonObject> TaskMatrixObj = ScenarioObject->GetObjectField(TEXT("taskMatrix"));
	ParseScenarioTaskMatrix(TaskMatrixObj);
	for (const TArray<TSharedPtr<FJsonValue>>& TaskMatrixJsonValues = ScenarioObject->GetArrayField(TEXT("taskMatrix"));
		 const TSharedPtr<FJsonValue>& TaskMatrixJsonValue : TaskMatrixJsonValues)
	{
		if (!TaskMatrixJsonValue.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: Scenario taskMatrix - skip invalid array element"));
			continue;
		}
		const TSharedPtr<FJsonObject> TaskMatrixJsonObject = TaskMatrixJsonValue->AsObject();
		ParseScenarioTaskMatrix(TaskMatrixJsonObject);
	}
}

void ADataManager::ParseScenarioEquipments(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: ParseScenarioEquipments - invalid json object"));
		return;
	}

	{
		TArray<FDroneInfo> DroneInfos;
		for (const TArray<TSharedPtr<FJsonValue>>& DroneList = InJsonObject->GetArrayField(TEXT("droneEntityList"));
			 const TSharedPtr<FJsonValue>& DroneJsonValue : DroneList)
		{
			if (!DroneJsonValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: droneEntityList - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> DroneJsonObject = DroneJsonValue->AsObject();
			if (!DroneJsonObject.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: droneEntityList - skip non-object array element"));
				continue;
			}

			FDroneInfo DroneInfo;
			DroneJsonObject->TryGetStringField(TEXT("equipmentCode"), DroneInfo.Id);
			DroneJsonObject->TryGetStringField(TEXT("name"), DroneInfo.Name);

			const TSharedPtr<FJsonObject> LocationJsonObject = DroneJsonObject->GetObjectField(TEXT("data"));
			if (LocationJsonObject.IsValid())
			{
				LocationJsonObject->TryGetNumberField(TEXT("x"), DroneInfo.Location.X);
				LocationJsonObject->TryGetNumberField(TEXT("y"), DroneInfo.Location.Y);
				LocationJsonObject->TryGetNumberField(TEXT("z"), DroneInfo.Location.Z);
			}
			else
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: drone entity missing 'data' (id=%s)"), *DroneInfo.Id);
			}

			DroneInfos.Add(DroneInfo);
		}
		FEquipmentController::Get()->CreateDrones(DroneInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d drone(s)"), DroneInfos.Num());
	}
	{
		TArray<FCarInfo> CarInfos;
		for (const TArray<TSharedPtr<FJsonValue>>& CarList = InJsonObject->GetArrayField(TEXT("autoVehicleEntityList"));
			 const TSharedPtr<FJsonValue>& CarJsonValue : CarList)
		{
			if (!CarJsonValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: autoVehicleEntityList - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> DroneJsonObject = CarJsonValue->AsObject();
			if (!DroneJsonObject.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: autoVehicleEntityList - skip non-object array element"));
				continue;
			}

			FCarInfo CarInfo;
			DroneJsonObject->TryGetStringField(TEXT("equipmentCode"), CarInfo.Id);
			DroneJsonObject->TryGetStringField(TEXT("name"), CarInfo.Name);

			const TSharedPtr<FJsonObject> LocationJsonObject = DroneJsonObject->GetObjectField(TEXT("data"));
			if (LocationJsonObject.IsValid())
			{
				LocationJsonObject->TryGetNumberField(TEXT("x"), CarInfo.Location.X);
				LocationJsonObject->TryGetNumberField(TEXT("y"), CarInfo.Location.Y);
				LocationJsonObject->TryGetNumberField(TEXT("z"), CarInfo.Location.Z);
			}
			else
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: car entity missing 'data' (id=%s)"), *CarInfo.Id);
			}

			CarInfos.Add(CarInfo);
		}
		FEquipmentController::Get()->CreateCars(CarInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d car(s)"), CarInfos.Num());
	}
	{
		TArray<FDogInfo> DogInfos;
		for (const TArray<TSharedPtr<FJsonValue>>& DroneList = InJsonObject->GetArrayField(TEXT("unmannedDogEntityList"));
			 const TSharedPtr<FJsonValue>& DroneJsonValue : DroneList)
		{
			if (!DroneJsonValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: unmannedDogEntityList - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> DroneJsonObject = DroneJsonValue->AsObject();
			if (!DroneJsonObject.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: unmannedDogEntityList - skip non-object array element"));
				continue;
			}

			FDogInfo DogInfo;
			DroneJsonObject->TryGetStringField(TEXT("equipmentCode"), DogInfo.Id);
			DroneJsonObject->TryGetStringField(TEXT("name"), DogInfo.Name);

			const TSharedPtr<FJsonObject> LocationJsonObject = DroneJsonObject->GetObjectField(TEXT("data"));
			if (LocationJsonObject.IsValid())
			{
				LocationJsonObject->TryGetNumberField(TEXT("x"), DogInfo.Location.X);
				LocationJsonObject->TryGetNumberField(TEXT("y"), DogInfo.Location.Y);
				LocationJsonObject->TryGetNumberField(TEXT("z"), DogInfo.Location.Z);
				LocationJsonObject->TryGetNumberField(TEXT("scale"), DogInfo.Scale);
			}
			else
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: dog entity missing 'data' (id=%s)"), *DogInfo.Id);
			}
			DogInfos.Add(DogInfo);
		}
		FEquipmentController::Get()->CreateDogs(DogInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d dog(s)"), DogInfos.Num());
	}
	{
		TArray<FShipInfo> ShipInfos;
		for (const TArray<TSharedPtr<FJsonValue>>& ShipList = InJsonObject->GetArrayField(TEXT("shipEntityList"));
			 const TSharedPtr<FJsonValue>& ShipJsonValue : ShipList)
		{
			if (!ShipJsonValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: shipEntityList - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> ShipJsonObject = ShipJsonValue->AsObject();
			if (!ShipJsonObject.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: shipEntityList - skip non-object array element"));
				continue;
			}

			FShipInfo ShipInfo;
			ShipJsonObject->TryGetStringField(TEXT("equipmentCode"), ShipInfo.Id);
			ShipJsonObject->TryGetStringField(TEXT("name"), ShipInfo.Name);

			const TSharedPtr<FJsonObject> DataJsonObject = ShipJsonObject->GetObjectField(TEXT("data"));
			if (DataJsonObject.IsValid())
			{
				DataJsonObject->TryGetNumberField(TEXT("X"), ShipInfo.Location.X);
				DataJsonObject->TryGetNumberField(TEXT("Y"), ShipInfo.Location.Y);
				DataJsonObject->TryGetNumberField(TEXT("Z"), ShipInfo.Location.Z);
			}
			else
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: ship entity missing 'data' (id=%s)"), *ShipInfo.Id);
			}
			ShipJsonObject->TryGetNumberField(TEXT("heading"), ShipInfo.Heading);

			ShipInfos.Add(ShipInfo);
		}
		FEquipmentController::Get()->CreateShips(ShipInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d ship(s)"), ShipInfos.Num());
	}
}

void ADataManager::ParseScenarioTaskMatrix(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Verbose, TEXT("ADataManager: ParseScenarioTaskMatrix - invalid json object (taskMatrix entry skipped)"));
		return;
	}

	// taskLevel
	// task_id
	// goal
	// initial_state
	const TSharedPtr<FJsonObject> InitialStateObj = InJsonObject->GetObjectField(TEXT("initial_state"));
	if (!InitialStateObj.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: taskMatrix missing 'initial_state'"));
		return;
	}

	FTaskMatrixController* Controller = FTaskMatrixController::Get();

	// goalFirePosition
	if (const TArray<TSharedPtr<FJsonValue>>* FirePosArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("goalFirePosition"), FirePosArray))
	{
		TArray<FFirePositionInfo> FirePositionInfos;
		for (const TSharedPtr<FJsonValue>& FirePosValue : *FirePosArray)
		{
			if (!FirePosValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: goalFirePosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> FirePosObj = FirePosValue->AsObject();
			if (!FirePosObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: goalFirePosition - skip non-object array element"));
				continue;
			}
			FFirePositionInfo FirePos;
			FirePosObj->TryGetStringField(TEXT("fireId"), FirePos.FireId);
			FirePosObj->TryGetNumberField(TEXT("X"), FirePos.Position.X);
			FirePosObj->TryGetNumberField(TEXT("Y"), FirePos.Position.Y);
			FirePosObj->TryGetNumberField(TEXT("Z"), FirePos.Position.Z);
			FirePosObj->TryGetNumberField(TEXT("scale"), FirePos.Scale);
			FirePositionInfos.Add(FirePos);
		}
		Controller->CreateFires(FirePositionInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d fire position(s)"), FirePositionInfos.Num());
	}
	// congestionPoints
	if (const TArray<TSharedPtr<FJsonValue>>* CongestionArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("congestionPoints"), CongestionArray))
	{
		TArray<FCongestionInfo> CongestionInfos;
		for (const TSharedPtr<FJsonValue>& CongestionValue : *CongestionArray)
		{
			if (!CongestionValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: congestionPoints - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> CongestionObj = CongestionValue->AsObject();
			if (!CongestionObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: congestionPoints - skip non-object array element"));
				continue;
			}
			FCongestionInfo CongestionInfo;
			CongestionObj->TryGetStringField(TEXT("conId"), CongestionInfo.ConId);
			CongestionObj->TryGetNumberField(TEXT("X"), CongestionInfo.Position.X);
			CongestionObj->TryGetNumberField(TEXT("Y"), CongestionInfo.Position.Y);
			CongestionObj->TryGetNumberField(TEXT("Z"), CongestionInfo.Position.Z);
			CongestionObj->TryGetNumberField(TEXT("yaw"), CongestionInfo.Yaw);
			CongestionInfos.Add(CongestionInfo);
		}
		Controller->CreateCongestions(CongestionInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d congestion point(s)"), CongestionInfos.Num());
	}
	// rescuePersonPosition
	if (const TArray<TSharedPtr<FJsonValue>>* RescueArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("rescuePersonPosition"), RescueArray))
	{
		TArray<FRescuePersonInfo> RescuePersonInfos;
		for (const TSharedPtr<FJsonValue>& RescueValue : *RescueArray)
		{
			if (!RescueValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: rescuePersonPosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> RescueObj = RescueValue->AsObject();
			if (!RescueObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: rescuePersonPosition - skip non-object array element"));
				continue;
			}
			FRescuePersonInfo RescueInfo;
			RescueObj->TryGetStringField(TEXT("personId"), RescueInfo.PersonId);
			RescueObj->TryGetNumberField(TEXT("X"), RescueInfo.Position.X);
			RescueObj->TryGetNumberField(TEXT("Y"), RescueInfo.Position.Y);
			RescueObj->TryGetNumberField(TEXT("Z"), RescueInfo.Position.Z);
			RescuePersonInfos.Add(RescueInfo);
		}
		Controller->CreateRescuePersons(RescuePersonInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d rescue person(s)"), RescuePersonInfos.Num());
	}
	// pollutionPosition
	if (const TArray<TSharedPtr<FJsonValue>>* PollutionArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("pollutionPosition"), PollutionArray))
	{
		TArray<FPollutionInfo> PollutionInfos;
		for (const TSharedPtr<FJsonValue>& PollutionValue : *PollutionArray)
		{
			if (!PollutionValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: pollutionPosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> PollutionObj = PollutionValue->AsObject();
			if (!PollutionObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: pollutionPosition - skip non-object array element"));
				continue;
			}
			FPollutionInfo PollutionInfo;
			PollutionObj->TryGetStringField(TEXT("pollutionId"), PollutionInfo.PollutionId);
			PollutionObj->TryGetNumberField(TEXT("X"), PollutionInfo.Position.X);
			PollutionObj->TryGetNumberField(TEXT("Y"), PollutionInfo.Position.Y);
			PollutionObj->TryGetNumberField(TEXT("Z"), PollutionInfo.Position.Z);
			PollutionInfos.Add(PollutionInfo);
		}
		Controller->CreatePollutions(PollutionInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d pollution position(s)"), PollutionInfos.Num());
	}
	// pipelineLeakPosition
	if (const TArray<TSharedPtr<FJsonValue>>* PipelineArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("pipelineLeakPosition"), PipelineArray))
	{
		TArray<FPipelineLeakInfo> PipelineInfos;
		for (const TSharedPtr<FJsonValue>& PipelineValue : *PipelineArray)
		{
			if (!PipelineValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: pipelineLeakPosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> PipelineObj = PipelineValue->AsObject();
			if (!PipelineObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: pipelineLeakPosition - skip non-object array element"));
				continue;
			}
			FPipelineLeakInfo PipelineInfo;
			PipelineObj->TryGetStringField(TEXT("pipeId"), PipelineInfo.PipeId);
			PipelineObj->TryGetNumberField(TEXT("X"), PipelineInfo.Position.X);
			PipelineObj->TryGetNumberField(TEXT("Y"), PipelineInfo.Position.Y);
			PipelineObj->TryGetNumberField(TEXT("Z"), PipelineInfo.Position.Z);
			PipelineInfos.Add(PipelineInfo);
		}
		Controller->CreatePipelineLeaks(PipelineInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d pipeline leak(s)"), PipelineInfos.Num());
	}
	// warehousePosition
	if (const TArray<TSharedPtr<FJsonValue>>* WarehouseArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("warehousePosition"), WarehouseArray))
	{
		TArray<FWarehouseInfo> WarehouseInfos;
		for (const TSharedPtr<FJsonValue>& WarehouseValue : *WarehouseArray)
		{
			if (!WarehouseValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: warehousePosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> WarehouseObj = WarehouseValue->AsObject();
			if (!WarehouseObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: warehousePosition - skip non-object array element"));
				continue;
			}
			FWarehouseInfo WarehouseInfo;
			WarehouseObj->TryGetStringField(TEXT("warehouseId"), WarehouseInfo.WarehouseId);
			WarehouseObj->TryGetNumberField(TEXT("X"), WarehouseInfo.Position.X);
			WarehouseObj->TryGetNumberField(TEXT("Y"), WarehouseInfo.Position.Y);
			WarehouseObj->TryGetNumberField(TEXT("Z"), WarehouseInfo.Position.Z);
			WarehouseInfos.Add(WarehouseInfo);
		}
		Controller->CreateWarehouses(WarehouseInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d warehouse(s)"), WarehouseInfos.Num());
	}
	// goalDelPosition
	if (const TArray<TSharedPtr<FJsonValue>>* DelArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("goalDelPosition"), DelArray))
	{
		TArray<FDeliveryInfo> DeliveryInfos;
		for (const TSharedPtr<FJsonValue>& DelValue : *DelArray)
		{
			if (!DelValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: goalDelPosition - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> DelObj = DelValue->AsObject();
			if (!DelObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: goalDelPosition - skip non-object array element"));
				continue;
			}
			FDeliveryInfo DelInfo;
			DelObj->TryGetStringField(TEXT("delId"), DelInfo.DelId);
			DelObj->TryGetNumberField(TEXT("X"), DelInfo.Position.X);
			DelObj->TryGetNumberField(TEXT("Y"), DelInfo.Position.Y);
			DelObj->TryGetNumberField(TEXT("Z"), DelInfo.Position.Z);
			DelObj->TryGetNumberField(TEXT("weight"), DelInfo.Weight);
			DeliveryInfos.Add(DelInfo);
		}
		Controller->CreateDeliveries(DeliveryInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d delivery position(s)"), DeliveryInfos.Num());
	}
	// queuingList
	if (const TArray<TSharedPtr<FJsonValue>>* QueuingArray = nullptr;
		InitialStateObj->TryGetArrayField(TEXT("queuingList"), QueuingArray))
	{
		TArray<FQueuingInfo> QueuingInfos;
		for (const TSharedPtr<FJsonValue>& QueuingValue : *QueuingArray)
		{
			if (!QueuingValue.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: queuingList - skip invalid array element"));
				continue;
			}
			const TSharedPtr<FJsonObject> QueuingObj = QueuingValue->AsObject();
			if (!QueuingObj.IsValid())
			{
				UE_LOG(LogTemp, Verbose, TEXT("ADataManager: queuingList - skip non-object array element"));
				continue;
			}
			FQueuingInfo QueuingInfo;
			QueuingObj->TryGetStringField(TEXT("queueId"), QueuingInfo.QueueId);
			QueuingObj->TryGetNumberField(TEXT("x"), QueuingInfo.Location.X);
			QueuingObj->TryGetNumberField(TEXT("y"), QueuingInfo.Location.Y);
			QueuingObj->TryGetNumberField(TEXT("z"), QueuingInfo.Location.Z);
			QueuingObj->TryGetNumberField(TEXT("heading"), QueuingInfo.Heading);
			QueuingObj->TryGetNumberField(TEXT("personCount"), QueuingInfo.PersonCount);
			QueuingObj->TryGetNumberField(TEXT("spacing"), QueuingInfo.Spacing);
			QueuingInfos.Add(QueuingInfo);
		}
		Controller->CreateQueues(QueuingInfos);
		UE_LOG(LogTemp, Log, TEXT("ADataManager: Parsed %d queuing point(s)"), QueuingInfos.Num());
	}
}

void ADataManager::OnReceiveTakePhotoTask(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveTakePhotoTask - invalid json object"));
		return;
	}

	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Green, FString::Printf(TEXT("DataManager: TakePhoto Task Received")));

	FString TaskId;
	InJsonObject->TryGetStringField(TEXT("taskId"), TaskId);

	for (const TArray<TSharedPtr<FJsonValue>>& ModelIdList = InJsonObject->GetArrayField(TEXT("modelIdList"));
		 const TSharedPtr<FJsonValue>& JsonValue : ModelIdList)
	{
		if (!JsonValue.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: TakePhoto modelIdList - skip invalid array element"));
			continue;
		}
		const TSharedPtr<FJsonObject> TaskJsonObject = JsonValue->AsObject();
		if (!TaskJsonObject.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: TakePhoto modelIdList - skip non-object array element"));
			continue;
		}

		FPhotoTaskInfo TaskInfo;
		// EquipmentType & EquipmentId
		if (TaskJsonObject->TryGetStringField(TEXT("droneId"), TaskInfo.EquipmentId);
			!TaskInfo.EquipmentId.IsEmpty())
		{
			TaskInfo.EquipmentType = 1;		// Drone
		}
		else if (TaskJsonObject->TryGetStringField(TEXT("carId"), TaskInfo.EquipmentId);
				 !TaskInfo.EquipmentId.IsEmpty())
		{
			TaskInfo.EquipmentType = 2;		// Car
		}
		else if (TaskJsonObject->TryGetStringField(TEXT("dogId"), TaskInfo.EquipmentId);
				 !TaskInfo.EquipmentId.IsEmpty())
		{
			TaskInfo.EquipmentType = 3;		// Dog
		}
		else
		{
			GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow, FString::Printf(TEXT("DataManager: TakePhoto Task, EquipmentId is Empty")));
		}

		// PhotoId
		TaskJsonObject->TryGetStringField(TEXT("Photoid"), TaskInfo.PhotoId);

		// ViewType
		FString ViewTypeStr;
		TaskJsonObject->TryGetStringField(TEXT("viewType"), ViewTypeStr);
		if (ViewTypeStr == TEXT("global"))
		{
			TaskInfo.ViewType = 1;		// Global
		}
		else if (ViewTypeStr == TEXT("topdown"))
		{
			TaskInfo.ViewType = 2;		// TopDown
		}
		else if (ViewTypeStr == TEXT("front"))
		{
			TaskInfo.ViewType = 3;		// Front
		}

		// Fields: serialize uploadSpec.fields back to JSON string
		const TSharedPtr<FJsonObject> UploadSpecObj = TaskJsonObject->GetObjectField(TEXT("uploadSpec"));
		if (UploadSpecObj.IsValid())
		{
			// Url
			if (FString Url;
				UploadSpecObj->TryGetStringField(TEXT("url"), Url))
			{
				TaskInfo.UploadUrl = Url;
			}
			// FileField
			if (FString FileField;
				UploadSpecObj->TryGetStringField(TEXT("fileField"), FileField))
			{
				TaskInfo.FileField = FileField;
			}
			// Fields
			if (const TSharedPtr<FJsonObject>* FieldsObj = nullptr;
				UploadSpecObj->TryGetObjectField(TEXT("fields"), FieldsObj))
			{
				TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&TaskInfo.Fields);
				FJsonSerializer::Serialize(FieldsObj->ToSharedRef(), Writer);
			}
		}
		else
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: TakePhoto missing 'uploadSpec' (photo=%s)"), *TaskInfo.PhotoId);
		}

		UE_LOG(LogTemp, Log, TEXT("ADataManager: TakePhoto task (equipType=%d, equipId=%s, photo=%s, view=%d)"),
			TaskInfo.EquipmentType, *TaskInfo.EquipmentId, *TaskInfo.PhotoId, TaskInfo.ViewType);

		if (AEquipmentActor* EquipmentActor = FEquipmentController::Get()->GetEquipment(TaskInfo.EquipmentId))
		{
			EquipmentActor->ExecuteTakePhotoTask(TaskInfo);
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("ADataManager: TakePhoto equipment not found: %s"), *TaskInfo.EquipmentId);
		}
	}
}

void ADataManager::OnReceiveEquipmentMoveTask2D(const TSharedPtr<FJsonObject>& InJsonObject)
{
	if (!InJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: OnReceiveEquipmentMoveTask2D - invalid json object"));
		return;
	}

	const TSharedPtr<FJsonObject> DataJsonObject = InJsonObject->GetObjectField(TEXT("data"));
	if (!DataJsonObject.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: EquipmentMoveTask2D missing 'data' field"));
		return;
	}
	FEquipmentMoveTask2D EquipmentMoveTask2D;
	DataJsonObject->TryGetStringField(TEXT("shipId"), EquipmentMoveTask2D.ShipId);
	for (const TArray<TSharedPtr<FJsonValue>>& TargetPositionJsonValues = DataJsonObject->GetArrayField(TEXT("targetPosition"));
		 const TSharedPtr<FJsonValue>& TargetPositionJsonValue : TargetPositionJsonValues)
	{
		if (!TargetPositionJsonValue.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: MoveTask2D targetPosition - skip invalid array element"));
			continue;
		}
		const TSharedPtr<FJsonObject> TargetPositionJsonObject = TargetPositionJsonValue->AsObject();
		if (!TargetPositionJsonObject.IsValid())
		{
			UE_LOG(LogTemp, Verbose, TEXT("ADataManager: MoveTask2D targetPosition - skip non-object array element"));
			continue;
		}
		FVector2D TargetPosition = FVector2D::ZeroVector;
		TargetPositionJsonObject->TryGetNumberField(TEXT("X"), TargetPosition.X);
		TargetPositionJsonObject->TryGetNumberField(TEXT("Y"), TargetPosition.Y);
		EquipmentMoveTask2D.TargetPositions.Add(TargetPosition);
	}
	DataJsonObject->TryGetNumberField(TEXT("speed"), EquipmentMoveTask2D.Speed);

	UE_LOG(LogTemp, Log, TEXT("ADataManager: MoveTask2D received (ship=%s, points=%d, speed=%.2f)"),
		*EquipmentMoveTask2D.ShipId, EquipmentMoveTask2D.TargetPositions.Num(), EquipmentMoveTask2D.Speed);

	if (AShipActor* ShipActor = Cast<AShipActor>(FEquipmentController::Get()->GetEquipment(EquipmentMoveTask2D.ShipId)))
	{
		ShipActor->ExecuteEquipmentMoveTask2D(EquipmentMoveTask2D);
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ADataManager: MoveTask2D ship not found: %s"), *EquipmentMoveTask2D.ShipId);
	}
}

void ADataManager::ResetScene()
{
	FMainWidgetController::Get()->CreateMainWidget();
	FEquipmentController::Get()->ClearEquipments();
	FTaskMatrixController::Get()->ClearTaskPoints();
	TaskId = FString();
}

void ADataManager::OnWebSocketConnectionError(const FString& InError)
{
	UE_LOG(LogTemp, Warning, TEXT("ADataManager: WebSocket connection error: %s (reconnecting)"), *InError);
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
	FString::Printf(TEXT("ADataManager: WebSocket ConnectionError, Error: %s"), *InError));
	
	FLWebSocketClient::Get()->Connect(WEBSOCKET_URL);	
}

void ADataManager::OnWebSocketClosed(const int32 InStatusCode, const FString& InReason, const bool bWasClean)
{
	UE_LOG(LogTemp, Warning, TEXT("ADataManager: WebSocket closed (code=%d, reason=%s, clean=%d) (reconnecting)"), InStatusCode, *InReason, bWasClean);
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
		FString::Printf(TEXT("ADataManager: WebSocket Closed, StatusCode: %d, Reason: %s, WasClean: %d"), InStatusCode, *InReason, bWasClean));
	
	FLWebSocketClient::Get()->Connect(WEBSOCKET_URL);	
}

void ADataManager::WebSocketSendMessage(const FString& InMessage)
{
	FLWebSocketClient::Get()->Send(InMessage);
}

void ADataManager::SendShipRescueMessage(const FString& InShipId, const int32 InDuringSeconds, const bool bSucceed,
	const FString& InPersonId, const FVector& InShipLocation) const
{
	const TSharedRef<FJsonObject> MessageJson = MakeShared<FJsonObject>();
	MessageJson->SetStringField(TEXT("taskId"), TaskId);
	MessageJson->SetStringField(TEXT("shipId"), InShipId);
	MessageJson->SetStringField(TEXT("commandType"), TEXT("executionShipCompleted"));
	MessageJson->SetNumberField(TEXT("duringTime"), InDuringSeconds);
	MessageJson->SetBoolField(TEXT("isSuccess"), bSucceed);
	MessageJson->SetStringField(TEXT("personId"), InPersonId);

	const TSharedRef<FJsonObject> PositionJson = MakeShared<FJsonObject>();
	PositionJson->SetNumberField(TEXT("X"), InShipLocation.X);
	PositionJson->SetNumberField(TEXT("Y"), InShipLocation.Y);
	MessageJson->SetObjectField(TEXT("shipPosition"), PositionJson);

	FString Message;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Message);
	FJsonSerializer::Serialize(MessageJson, Writer);

	UE_LOG(LogTemp, Log, TEXT("ADataManager: SendShipRescue (ship=%s, person=%s, succeed=%d, during=%ds)"), *InShipId, *InPersonId, bSucceed, InDuringSeconds);
	WebSocketSendMessage(Message);
}
