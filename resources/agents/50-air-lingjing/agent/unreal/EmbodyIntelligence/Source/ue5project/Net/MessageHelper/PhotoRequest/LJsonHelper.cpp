#include "LJsonHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Dom/JsonObject.h"

FLJsonHelper* FLJsonHelper::Get()
{
	static FLJsonHelper Instance;
	return &Instance;
}

uint8 FLJsonHelper::GetCommandType(const FString& InMessage)
{
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
	FJsonSerializer::Deserialize(Reader, JsonObject);

	const FString CommandType = JsonObject->GetStringField(TEXT("commandType")); 
	if (CommandType.Contains(TEXT("takePhoto")))
	{
		return 1;
	}
	if (CommandType.Contains(TEXT("resetScenario")))
	{
		return 2;
	}
	
	return 255;
}

FString FLJsonHelper::GetCommandTypeAsString(const FString& InMessage)
{
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
	FJsonSerializer::Deserialize(Reader, JsonObject);
	
	if (const TSharedPtr<FJsonObject>* DataJsonObject = nullptr; 
		JsonObject->TryGetObjectField(TEXT("data"), DataJsonObject))
	{
		FString CommandType;
		(*DataJsonObject)->TryGetStringField(TEXT("commandType"), CommandType);
		return CommandType;
	}
	return FString();
}

uint8 FLJsonHelper::GetRequestType(const FString& InMessage)
{
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
	FJsonSerializer::Deserialize(Reader, JsonObject);
	
	const TSharedPtr<FJsonObject> DataJsonObject = JsonObject->GetObjectField(TEXT("data"));
	
	FString TaskId;
	DataJsonObject->TryGetStringField(TEXT("taskId"), TaskId);
	
	if (TaskId.Contains(TEXT("singledrone_fire")))
	{
		return 1;
	}
	if (TaskId.Contains(TEXT("bridge")))
	{
		return 2;
	}
	if (TaskId.Contains(TEXT("deliverytask")))
	{
		return 3;
	}
	if (TaskId.Contains(TEXT("deliverytask")))
	{
		return 4;
	}
	if (TaskId.Contains(TEXT("deliverytask")))
	{
		return 5;
	}
	if (TaskId.Contains(TEXT("singledog")))
	{
		return 6;
	}
	if (TaskId.Contains(TEXT("uavdog")))
	{
		return 7;
	}
	
	return 255;
}

void FLJsonHelper::ParsePhotoRequest(const FString& InMessage, TArray<FLPhotoTask>& PhotoTasks)
{
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InMessage);
	FJsonSerializer::Deserialize(Reader, JsonObject);

	const TSharedPtr<FJsonObject>* DataJsonObject = nullptr; 
	if (!JsonObject->TryGetObjectField(TEXT("data"), DataJsonObject))
	{
		return;
	}
	
	const TArray<TSharedPtr<FJsonValue>>* ModelIdList = nullptr;
	if (!(*DataJsonObject)->TryGetArrayField(TEXT("modelIdList"), ModelIdList) || ModelIdList->Num() == 0)
	{
		return;
	}

	PhotoTasks.Empty(ModelIdList->Num());

	for (const TSharedPtr<FJsonValue>& ItemValue : *ModelIdList)
	{
		const TSharedPtr<FJsonObject>* ItemObj = nullptr;
		if (!ItemValue->TryGetObject(ItemObj))
		{
			continue;
		}

		FLPhotoTask Task;

		// ModelType & ModelId
		FString DroneId, CarId, DogId;
		(*ItemObj)->TryGetStringField(TEXT("droneId"), DroneId);
		(*ItemObj)->TryGetStringField(TEXT("carId"), CarId);
		(*ItemObj)->TryGetStringField(TEXT("dogId"), DogId);

		if (!DroneId.IsEmpty())
		{
			Task.ModelType = 1;
			Task.ModelId = DroneId;
		}
		else if (!CarId.IsEmpty())
		{
			Task.ModelType = 2;
			Task.ModelId = CarId;
		}
		else if (!DogId.IsEmpty())
		{
			Task.ModelType = 3;
			Task.ModelId = DogId;
		}

		// ViewType
		FString ViewTypeStr;
		(*ItemObj)->TryGetStringField(TEXT("viewType"), ViewTypeStr);
		if (ViewTypeStr == TEXT("global"))
		{
			Task.ViewType = 1;
		}
		else if (ViewTypeStr == TEXT("topdown"))
		{
			Task.ViewType = 2;
		}
		else if (ViewTypeStr == TEXT("front"))
		{
			Task.ViewType = 3;
		}

		// Fields: serialize uploadSpec.fields back to JSON string
		if (const TSharedPtr<FJsonObject>* UploadSpecObj = nullptr; 
			(*ItemObj)->TryGetObjectField(TEXT("uploadSpec"), UploadSpecObj))
		{
			// Url
			if (FString Url; 
				(*UploadSpecObj)->TryGetStringField(TEXT("url"), Url))
			{
				Task.UploadUrl = Url;
			}
			// FileField
			if (FString FileField; 
				(*UploadSpecObj)->TryGetStringField(TEXT("fileField"), FileField))
			{
				Task.FileField = FileField;
			}
			// Fields
			if (const TSharedPtr<FJsonObject>* FieldsObj = nullptr; 
				(*UploadSpecObj)->TryGetObjectField(TEXT("fields"), FieldsObj))
			{
				TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Task.Fields);
				FJsonSerializer::Serialize(FieldsObj->ToSharedRef(), Writer);
			}
		}

		PhotoTasks.Add(MoveTemp(Task));
	}
}

